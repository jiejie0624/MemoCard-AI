import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "../api.js";
import { useLanguage } from "../i18n.jsx";

async function requestCards(path, options = {}) {
  const response = await fetch(apiUrl(`/api/flashcards${path}`), {
    method: options.method || "GET",
    credentials: "include",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: AbortSignal.timeout(15000),
  });
  if (response.status === 204) return null;
  let payload = null;
  try { payload = await response.json(); } catch { /* use fallback below */ }
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "闪卡操作失败，请稍后重试。");
  return payload;
}

function displayDueDate(value, locale) {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(value));
}

export default function FlashcardsPage() {
  const { t, locale } = useLanguage();
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState({ question: "", answer: "" });
  const [busyId, setBusyId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [confirmingGroup, setConfirmingGroup] = useState(null);
  const groupDialog = useRef(null);

  // Uses the project's native <dialog> so deleting a group looks and behaves like every
  // other destructive action, instead of the browser's confirm popup.
  useEffect(() => {
    const dialog = groupDialog.current;
    if (!dialog) return;
    if (confirmingGroup && !dialog.open) dialog.showModal();
    if (!confirmingGroup && dialog.open) dialog.close();
  }, [confirmingGroup]);

  const loadCards = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setCards(await requestCards(""));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadCards(); }, [loadCards]);

  function beginEdit(card) {
    setEditingId(card.id);
    setDraft({ question: card.question, answer: card.answer });
    setConfirmDeleteId(null);
    setError("");
  }

  async function saveEdit(event) {
    event.preventDefault();
    if (!editingId) return;
    setBusyId(editingId);
    setError("");
    try {
      const updated = await requestCards(`/${editingId}`, { method: "PATCH", body: draft });
      setCards((current) => current.map((card) => card.id === updated.id ? updated : card));
      setEditingId(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyId(null);
    }
  }

  async function deleteCard(cardId) {
    setBusyId(cardId);
    setError("");
    try {
      await requestCards(`/${cardId}`, { method: "DELETE" });
      setCards((current) => current.filter((card) => card.id !== cardId));
      setConfirmDeleteId(null);
      if (editingId === cardId) setEditingId(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyId(null);
    }
  }

  async function deleteGroup(group) {
    if (!group || !group.cards.length) return;
    setConfirmingGroup(null);
    setBusyId("group");
    setError("");
    try {
      // Deleted one by one because the API removes a single card; all of them belong to
      // the same document, so the group disappears as soon as the loop finishes.
      for (const card of group.cards) {
        await requestCards(`/${card.id}`, { method: "DELETE" });
      }
      setCards((current) => current.filter((card) => !group.cards.some((item) => item.id === card.id)));
    } catch (requestError) {
      setError(requestError.message);
      await loadCards();
    } finally {
      setBusyId(null);
    }
  }

  const dueCount = cards.filter((card) => new Date(card.next_review_at) <= new Date()).length;

  // One collapsible group per source document, matching the review calendar: deleting is
  // easier when every card from the same file sits together.
  const cardGroups = useMemo(() => {
    const groups = new Map();
    for (const card of cards) {
      const source = card.sources?.[0];
      const key = source?.document_id ?? "unsourced";
      if (!groups.has(key)) {
        groups.set(key, { key, name: source?.document_name ?? t("无来源的卡片"), cards: [] });
      }
      groups.get(key).cards.push(card);
    }
    return [...groups.values()];
  }, [cards, t]);

  return (
    <main className="flashcards-page">
      <header className="flashcards-heading">
        <div>
          <p className="eyebrow">{t("MEMOCARD AI · 知识卡片")}</p>
          <h1>{t("闪卡")}</h1>
          <p>{t("管理从学习问答中保存的卡片；复习与排期稍后接入。")}</p>
        </div>
        <div className="flashcards-summary" aria-label={t("闪卡统计")}>
          <span><strong>{cards.length}</strong> {t("张卡片")}</span>
          <span><strong>{dueCount}</strong> {t("张待复习")}</span>
        </div>
      </header>

      {error && <p className="flashcards-error" role="alert">{t(error)}</p>}
      {loading ? <p className="flashcards-status" role="status">{t("正在加载闪卡…")}</p> : !cards.length ? (
        <section className="flashcards-empty">
          <span aria-hidden="true">✦</span>
          <h2>{t("还没有保存的闪卡")}</h2>
          <p>{t("在 AI 问答中选择一条有资料引用的回答，生成并保存闪卡草稿。")}</p>
        </section>
      ) : (
        <section className="flashcards-list" aria-label={t("闪卡列表")}>
          {cardGroups.map((group) => (
            <details className="flashcards-group" key={group.key}>
              <summary>
                <span className="flashcards-group-name">{group.name}</span>
                <span className="flashcards-group-count">{t("{count} 张", { count: group.cards.length })}</span>
                <button
                  className="text-button is-danger flashcards-group-delete"
                  type="button"
                  disabled={busyId === "group"}
                  onClick={(event) => { event.preventDefault(); event.stopPropagation(); setConfirmingGroup(group); }}
                >
                  {t("删除整组")}
                </button>
              </summary>
              {group.cards.map((card) => (
            <article className="flashcard-row" key={card.id}>
              {editingId === card.id ? (
                <form className="flashcard-edit-form" onSubmit={saveEdit}>
                  <label>
                    <span>{t("问题")}</span>
                    <textarea value={draft.question} maxLength={2000} required
                      onChange={(event) => setDraft((current) => ({ ...current, question: event.target.value }))} />
                  </label>
                  <label>
                    <span>{t("答案")}</span>
                    <textarea value={draft.answer} maxLength={5000} required
                      onChange={(event) => setDraft((current) => ({ ...current, answer: event.target.value }))} />
                  </label>
                  <div className="flashcard-actions">
                    <button className="cancel-button" type="button" onClick={() => setEditingId(null)} disabled={busyId === card.id}>{t("取消")}</button>
                    <button className="primary-button" type="submit" disabled={busyId === card.id}>{busyId === card.id ? t("保存中…") : t("保存修改")}</button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="flashcard-content">
                    <h2>{card.question}</h2>
                    {/* A memory tool should not show the answer before the attempt. */}
                    <details className="flashcard-answer">
                      <summary>{t("显示答案")}</summary>
                      <p>{card.answer}</p>
                    </details>
                    <div className="flashcard-sources">
                      {card.sources.map((source) => (
                        <span key={`${source.document_id}-${source.document_chunk_id}`}>{source.document_name}</span>
                      ))}
                    </div>
                  </div>
                  <div className="flashcard-meta">
                    <span>{t("下次复习：")} {displayDueDate(card.next_review_at, locale)}</span>
                    <div className="flashcard-actions">
                      <button className="text-button" type="button" onClick={() => beginEdit(card)}>{t("编辑")}</button>
                      {confirmDeleteId === card.id ? (
                        <span className="flashcard-delete-confirm">
                          {t("删除这张卡？")}
                          <button className="text-button is-danger" type="button" disabled={busyId === card.id} onClick={() => deleteCard(card.id)}>{t("确认")}</button>
                          <button className="text-button" type="button" onClick={() => setConfirmDeleteId(null)}>{t("取消")}</button>
                        </span>
                      ) : (
                        <button className="text-button is-danger" type="button" onClick={() => setConfirmDeleteId(card.id)}>{t("删除")}</button>
                      )}
                    </div>
                  </div>
                </>
              )}
            </article>
              ))}
            </details>
          ))}
        </section>
      )}
      <dialog
        ref={groupDialog}
        className="profile-dialog"
        aria-labelledby="flashcard-group-delete-title"
        onCancel={(event) => { event.preventDefault(); setConfirmingGroup(null); }}
        onClose={() => setConfirmingGroup(null)}
      >
        <div className="profile-dialog-heading">
          <div>
            <p className="eyebrow">{t("删除整组")}</p>
            <h2 id="flashcard-group-delete-title">{t("删除这个文件下的全部卡片？")}</h2>
          </div>
          <button className="dialog-close" type="button" aria-label={t("取消删除")} onClick={() => setConfirmingGroup(null)}>×</button>
        </div>
        <p className="document-delete-copy">
          {confirmingGroup?.name}{t("的 {count} 张卡片都会被删除，删除后无法恢复。", { count: confirmingGroup?.cards.length ?? 0 })}
        </p>
        <div className="profile-actions">
          <button className="cancel-button" type="button" onClick={() => setConfirmingGroup(null)} disabled={busyId === "group"}>{t("取消")}</button>
          <button className="danger-button" type="button" onClick={() => deleteGroup(confirmingGroup)} disabled={busyId === "group"}>
            {busyId === "group" ? t("正在删除…") : t("确认删除")}
          </button>
        </div>
      </dialog>
    </main>
  );
}
