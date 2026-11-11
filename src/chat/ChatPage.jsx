import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "../api.js";
import { useLanguage } from "../i18n.jsx";

const API = "/api/chat";

async function chatRequest(path, options = {}) {
  const response = await fetch(apiUrl(`${API}${path}`), {
    method: options.method || "GET",
    credentials: "include",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: AbortSignal.timeout(60000),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // Show a short fallback if a proxy returns a non-JSON error.
  }
  if (!response.ok) {
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "暂时无法完成请求，请稍后重试。");
  }
  return payload;
}

async function flashcardRequest(path, options = {}) {
  const response = await fetch(apiUrl(`/api/flashcards${path}`), {
    method: options.method || "GET",
    credentials: "include",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: AbortSignal.timeout(60000),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "闪卡操作失败，请稍后重试。");
  return payload;
}

function formatSessionTitle(session, t) {
  return session.title || t("新对话");
}

function CitationList({ citations }) {
  const { t } = useLanguage();
  if (!citations?.length) return null;
  return (
    <details className="chat-citations">
      <summary>{t("查看 {count} 个资料来源", { count: citations.length })}</summary>
      <ol>
        {citations.map((citation) => (
          <li key={`${citation.rank}-${citation.document_name}-${citation.page_number}-${citation.slide_number}`}>
            <strong>{citation.document_name}</strong>
            {(citation.page_number || citation.slide_number) && (
              <span>{citation.page_number ? t(" · 第 {page} 页", { page: citation.page_number }) : t(" · 第 {slide} 张", { slide: citation.slide_number })}</span>
            )}
            <p>{citation.excerpt}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

export default function ChatPage({ onOpenDocuments, onOpenFlashcards }) {
  const { t } = useLanguage();
  const [documents, setDocuments] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [showScope, setShowScope] = useState(false);
  const [draftSource, setDraftSource] = useState(null);
  const [draftCards, setDraftCards] = useState([]);
  const [generatingDraft, setGeneratingDraft] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [draftError, setDraftError] = useState("");
  const [confirmingSession, setConfirmingSession] = useState(null);
  const [deletingSession, setDeletingSession] = useState(false);
  const bottomRef = useRef(null);
  const deleteDialog = useRef(null);

  const readyDocuments = documents.filter((document) => document.status === "ready");

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextDocuments, nextSessions] = await Promise.all([
        fetch(apiUrl("/api/documents"), { credentials: "include", signal: AbortSignal.timeout(15000) }).then(async (response) => {
          if (!response.ok) throw new Error("无法加载学习资料。");
          return response.json();
        }),
        chatRequest("/sessions"),
      ]);
      setDocuments(nextDocuments);
      setSessions(nextSessions);
      if (nextSessions.length) {
        const first = nextSessions[0];
        setActiveSession(first);
        setSelectedDocumentIds(first.selected_document_ids || []);
        setMessages(await chatRequest(`/sessions/${first.id}/messages`));
      } else {
        setActiveSession(null);
        setMessages([]);
      }
    } catch (requestError) {
      setError(requestError.message || "无法连接问答服务。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  // The native dialog owns focus and Esc; state only decides whether it is open, so a
  // cancelled deletion restores the trigger instead of leaving the page in a stale state.
  useEffect(() => {
    const dialog = deleteDialog.current;
    if (!dialog) return;
    if (confirmingSession && !dialog.open) dialog.showModal();
    if (!confirmingSession && dialog.open) dialog.close();
  }, [confirmingSession]);

  function startNewSession() {
    setActiveSession(null);
    setMessages([]);
    setSelectedDocumentIds([]);
    setQuestion("");
    setError("");
    setShowScope(false);
  }

  async function openSession(session) {
    setActiveSession(session);
    setSelectedDocumentIds(session.selected_document_ids || []);
    setError("");
    try {
      setMessages(await chatRequest(`/sessions/${session.id}/messages`));
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function deleteSession(session) {
    if (!session || deletingSession) return;
    setDeletingSession(true);
    setError("");
    try {
      await chatRequest(`/sessions/${session.id}`, { method: "DELETE" });
      setConfirmingSession(null);
      // The removed chat may be the one on screen: clear it rather than leaving a
      // thread that still claims to belong to a conversation that no longer exists.
      if (activeSession?.id === session.id) {
        setActiveSession(null);
        setMessages([]);
        setSelectedDocumentIds([]);
      }
      setSessions(await chatRequest("/sessions"));
    } catch (requestError) {
      setError(requestError.message);
      setConfirmingSession(null);
    } finally {
      setDeletingSession(false);
    }
  }

  function toggleDocument(documentId) {
    setSelectedDocumentIds((current) => current.includes(documentId)
      ? current.filter((id) => id !== documentId)
      : [...current, documentId]);
  }

  async function submitQuestion(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text || sending || !readyDocuments.length) return;
    setSending(true);
    setError("");
    try {
      let session = activeSession;
      if (!session) {
        session = await chatRequest("/sessions", {
          method: "POST",
          body: selectedDocumentIds.length ? { selected_document_ids: selectedDocumentIds } : {},
        });
        setActiveSession(session);
      }
      const updatedMessages = await chatRequest(`/sessions/${session.id}/messages`, {
        method: "POST",
        body: { question: text },
      });
      setMessages(updatedMessages);
      setQuestion("");
      setSessions(await chatRequest("/sessions"));
    } catch (requestError) {
      setError(requestError.message || "AI 暂时无法回答，请重试。");
    } finally {
      setSending(false);
    }
  }

  async function generateCards(message) {
    setDraftSource(message);
    setDraftCards([]);
    setDraftError("");
    setGeneratingDraft(true);
    try {
      const result = await flashcardRequest("/generate", {
        method: "POST",
        body: { source_message_id: message.id },
      });
      setDraftCards(result.cards);
    } catch (requestError) {
      setDraftError(requestError.message);
    } finally {
      setGeneratingDraft(false);
    }
  }

  function updateDraft(index, field, value) {
    setDraftCards((current) => current.map((card, cardIndex) =>
      cardIndex === index ? { ...card, [field]: value } : card,
    ));
  }

  async function saveDraftCards() {
    if (!draftSource || !draftCards.length) return;
    setSavingDraft(true);
    setDraftError("");
    try {
      await flashcardRequest("", {
        method: "POST",
        body: { source_message_id: draftSource.id, cards: draftCards },
      });
      setDraftSource(null);
      setDraftCards([]);
      onOpenFlashcards();
    } catch (requestError) {
      setDraftError(requestError.message);
    } finally {
      setSavingDraft(false);
    }
  }

  if (loading) {
    return <main className="chat-page"><p className="chat-loading" role="status">{t("正在整理你的对话…")}</p></main>;
  }

  return (
    <main className="chat-page">
      <header className="chat-page-heading">
        <div>
          <p className="eyebrow">{t("MEMOCARD AI · 学习问答")}</p>
          <h1>{t("AI 问答")}</h1>
          <p>{t("结合已处理的课程资料回答，并附上可核对的来源。")}</p>
        </div>
        <button className="primary-button chat-new-button" type="button" onClick={startNewSession}>
          {t("新建对话")}
        </button>
      </header>

      <section className="chat-workspace" aria-label={t("AI 问答工作区")}>
        <aside className="chat-session-list" aria-label={t("对话历史")}>
          <div className="chat-session-list-heading">
            <h2>{t("对话")}</h2>
            <span>{sessions.length}</span>
          </div>
          {sessions.length ? sessions.map((session) => (
            <div className="chat-session-row" key={session.id}>
              <button
                className={`chat-session-item${activeSession?.id === session.id ? " is-active" : ""}`}
                type="button"
                onClick={() => openSession(session)}
              >
                <strong>{formatSessionTitle(session, t)}</strong>
                <span>{session.message_count || 0} {t("条消息")}</span>
              </button>
              <button
                className="chat-session-delete"
                type="button"
                onClick={() => setConfirmingSession(session)}
                aria-label={t("删除对话：{title}", { title: formatSessionTitle(session, t) })}
              >
                {t("删除")}
              </button>
            </div>
          )) : <p className="chat-session-empty">{t("发送第一个问题后，对话会显示在这里。")}</p>}
        </aside>

        <div className="chat-thread">
          <div className="chat-thread-topline">
            <div>
              <strong>{activeSession ? formatSessionTitle(activeSession, t) : t("开始一个新对话")}</strong>
              <span>
                {activeSession?.all_documents === false
                  ? t("已选择 {count} 份资料", { count: selectedDocumentIds.length })
                  : t("搜索全部已就绪资料 · {count} 份", { count: readyDocuments.length })}
              </span>
            </div>
            {!activeSession && (
              <button className="text-button" type="button" onClick={() => setShowScope((value) => !value)}>
                {showScope ? t("收起资料选择") : t("选择资料")}
              </button>
            )}
          </div>

          {showScope && !activeSession && (
            <div className="chat-scope-panel" aria-label={t("选择本次对话资料")}>
              <p>{t("默认搜索全部已就绪资料。勾选后，只搜索选中的资料。")}</p>
              <div className="chat-scope-options">
                {readyDocuments.map((document) => (
                  <label key={document.id}>
                    <input
                      type="checkbox"
                      checked={selectedDocumentIds.includes(document.id)}
                      onChange={() => toggleDocument(document.id)}
                    />
                    <span>{document.original_filename}</span>
                  </label>
                ))}
              </div>
              {selectedDocumentIds.length > 0 && (
                <button className="text-button" type="button" onClick={() => setSelectedDocumentIds([])}>
                  {t("恢复搜索全部资料")}
                </button>
              )}
            </div>
          )}

          <div className="chat-message-list" aria-live="polite">
            {!messages.length && (
              <div className="chat-empty-state">
                <span className="chat-empty-mark" aria-hidden="true">✦</span>
                <h2>{readyDocuments.length ? t("你想从资料里了解什么？") : t("先准备一份学习资料")}</h2>
                <p>
                  {readyDocuments.length
                    ? t("我会先查找相关内容，再根据找到的片段回答并标出来源。")
                    : t("上传并处理 PDF、TXT 或 PPTX 后，就可以针对内容提问。")}
                </p>
                {!readyDocuments.length && (
                  <button className="secondary-button" type="button" onClick={onOpenDocuments}>
                    {t("前往学习资料")}
                  </button>
                )}
              </div>
            )}
            {messages.map((message) => (
              <article className={`chat-message chat-message-${message.role}`} key={message.id}>
                <div className="chat-message-label">{message.role === "user" ? t("你") : "MemoCard AI"}</div>
                <div className="chat-message-content">{message.content}</div>
                {message.role === "assistant" && (
                  <>
                    <CitationList citations={message.citations} />
                    {message.citations?.length > 0 && (
                      <button className="text-button chat-generate-cards" type="button"
                        onClick={() => generateCards(message)}>
                        {t("生成闪卡")}
                      </button>
                    )}
                  </>
                )}
              </article>
            ))}
            {sending && <p className="chat-thinking" role="status">{t("正在查找资料并整理回答…")}</p>}
            <div ref={bottomRef} />
          </div>

          {error && <p className="chat-error" role="alert">{t(error)}</p>}
          <form className="chat-composer" onSubmit={submitQuestion}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              maxLength={4000}
              rows={2}
              placeholder={readyDocuments.length ? t("输入关于课程资料的问题…") : t("处理好学习资料后即可提问")}
              disabled={!readyDocuments.length || sending}
              aria-label={t("输入问题")}
            />
            <button className="primary-button" type="submit" disabled={!question.trim() || sending || !readyDocuments.length}>
              {sending ? t("回答中…") : t("发送")}
            </button>
            <span>{t("Enter 发送 · Shift + Enter 换行")}</span>
          </form>
        </div>
      </section>

      {draftSource && (
        <div className="flashcard-draft-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !savingDraft && !generatingDraft) setDraftSource(null);
        }}>
          <section className="flashcard-draft-dialog" role="dialog" aria-modal="true" aria-labelledby="flashcard-draft-title">
            <header>
              <div>
                <p className="eyebrow">{t("来自 AI 回答")}</p>
                <h2 id="flashcard-draft-title">{t("检查闪卡草稿")}</h2>
              </div>
              <button type="button" className="dialog-close" aria-label={t("关闭闪卡草稿")}
                onClick={() => setDraftSource(null)} disabled={savingDraft || generatingDraft}>×</button>
            </header>
            <div className="flashcard-draft-body">
              {generatingDraft ? <p className="chat-thinking" role="status">{t("正在根据回答和引用整理闪卡…")}</p> : (
                <>
                  {draftCards.map((card, index) => (
                    <article className="flashcard-draft-item" key={`${index}-${card.question}`}>
                      <div className="flashcard-draft-item-heading">
                        <strong>{t("卡片 {count}", { count: index + 1 })}</strong>
                        <button className="text-button is-danger" type="button"
                          onClick={() => setDraftCards((current) => current.filter((_, cardIndex) => cardIndex !== index))}>
                          {t("移除此卡")}
                        </button>
                      </div>
                      <label><span>{t("问题")}</span><textarea value={card.question} maxLength={2000}
                        onChange={(event) => updateDraft(index, "question", event.target.value)} /></label>
                      <label><span>{t("答案")}</span><textarea value={card.answer} maxLength={5000}
                        onChange={(event) => updateDraft(index, "answer", event.target.value)} /></label>
                      <span className="flashcard-draft-source">{t("引用来源：")}{card.source_refs.map((rank) => t("来源 {rank}", { rank })).join(", ")}</span>
                    </article>
                  ))}
                  {!draftCards.length && !draftError && <p className="chat-session-empty">{t("没有可保存的草稿。")}</p>}
                </>
              )}
              {draftError && <p className="chat-error" role="alert">{t(draftError)}</p>}
            </div>
            <footer>
              <button className="cancel-button" type="button" onClick={() => setDraftSource(null)} disabled={savingDraft}>{t("取消")}</button>
              {!generatingDraft && draftError && !draftCards.length && (
                <button className="secondary-button" type="button" onClick={() => generateCards(draftSource)} disabled={savingDraft}>{t("重试生成")}</button>
              )}
              <button className="primary-button" type="button" onClick={saveDraftCards}
                disabled={generatingDraft || savingDraft || !draftCards.length}>
                {savingDraft ? t("正在保存…") : t("保存 {count} 张闪卡", { count: draftCards.length })}
              </button>
            </footer>
          </section>
        </div>
      )}
      <dialog
        ref={deleteDialog}
        className="profile-dialog"
        aria-labelledby="chat-delete-title"
        onCancel={(event) => {
          event.preventDefault();
          if (!deletingSession) setConfirmingSession(null);
        }}
        onClose={() => setConfirmingSession(null)}
      >
        <div className="profile-dialog-heading">
          <div>
            <p className="eyebrow">{t("删除对话")}</p>
            <h2 id="chat-delete-title">{t("确定删除这段对话？")}</h2>
          </div>
          <button
            className="dialog-close"
            type="button"
            aria-label={t("取消删除")}
            onClick={() => setConfirmingSession(null)}
            disabled={deletingSession}
          >
            ×
          </button>
        </div>
        <p className="document-delete-copy">
          {confirmingSession ? formatSessionTitle(confirmingSession, t) : ""}
          {t("及其中的消息会被移除；由它生成的闪卡会保留，可以继续复习。")}
        </p>
        <div className="profile-actions">
          <button
            className="cancel-button"
            type="button"
            onClick={() => setConfirmingSession(null)}
            disabled={deletingSession}
          >
            {t("保留对话")}
          </button>
          <button
            className="danger-button"
            type="button"
            onClick={() => confirmingSession && deleteSession(confirmingSession)}
            disabled={deletingSession}
          >
            {deletingSession ? t("正在删除…") : t("确认删除")}
          </button>
        </div>
      </dialog>
    </main>
  );
}
