import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "../api.js";
import { useLanguage } from "../i18n.jsx";
import { chatRequest, formatSessionTitle } from "./chatApi.js";

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

export default function ChatPage({
  activeSession,
  onSessionCreated,
  onRefreshSessions,
  onNewSession,
  onOpenDocuments,
  onOpenFlashcards,
}) {
  const { t } = useLanguage();
  const [documents, setDocuments] = useState([]);
  const [messages, setMessages] = useState([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [showScope, setShowScope] = useState(false);
  const [draftSource, setDraftSource] = useState(null);
  const [draftCards, setDraftCards] = useState([]);
  const [generatingDraft, setGeneratingDraft] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [draftError, setDraftError] = useState("");
  const bottomRef = useRef(null);
  // Tracks which conversation the transcript belongs to. It lets a turn that is still
  // being saved avoid clobbering a thread the user just switched to.
  const loadedSessionId = useRef(null);

  const readyDocuments = documents.filter((document) => document.status === "ready");

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/documents"), {
        credentials: "include",
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok) throw new Error("无法加载学习资料。");
      setDocuments(await response.json());
    } catch (requestError) {
      setError(requestError.message || "无法连接问答服务。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  // The selected conversation is owned by the app shell. Load its messages here and
  // clear the draft state when the shell starts a new chat.
  useEffect(() => {
    const sessionId = activeSession?.id ?? null;
    if (sessionId === loadedSessionId.current) return undefined;
    loadedSessionId.current = sessionId;

    if (!sessionId) {
      setMessages([]);
      setSelectedDocumentIds([]);
      setMessagesLoading(false);
      setQuestion("");
      setError("");
      setShowScope(false);
      return undefined;
    }

    let cancelled = false;
    setMessagesLoading(true);
    setError("");
    setSelectedDocumentIds(activeSession.selected_document_ids || []);
    chatRequest(`/sessions/${sessionId}/messages`)
      .then((nextMessages) => {
        if (!cancelled) setMessages(nextMessages);
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message);
      })
      .finally(() => {
        if (!cancelled) setMessagesLoading(false);
      });
    return () => { cancelled = true; };
  }, [activeSession]);

  function startNewSession() {
    setMessages([]);
    setSelectedDocumentIds([]);
    setQuestion("");
    setError("");
    setShowScope(false);
    onNewSession();
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
        // The first turn is saved below into this session; mark it loaded so the
        // message effect does not fetch an empty thread over the answer.
        loadedSessionId.current = session.id;
        onSessionCreated(session);
      }
      const updatedMessages = await chatRequest(`/sessions/${session.id}/messages`, {
        method: "POST",
        body: { question: text },
      });
      // A turn can finish after the user opens another chat. Only update the transcript
      // when the selected conversation is still the one that produced it.
      if (loadedSessionId.current === session.id) {
        setMessages(updatedMessages);
        setQuestion("");
      }
      // Refresh the nav's title and message count without blocking the answer.
      onRefreshSessions().catch(() => {});
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
        <div className="chat-heading-actions">
          <button className="primary-button chat-new-button" type="button" onClick={startNewSession}>
            {t("新建对话")}
          </button>
        </div>
      </header>

      <section className="chat-workspace" aria-label={t("AI 问答工作区")}>
        <div className="chat-thread">
          <div className="chat-thread-topline">
            <div>
              <strong>{activeSession ? formatSessionTitle(activeSession, t) : t("开始一个新对话")}</strong>
              <span>
                {activeSession?.all_documents === false
                  ? selectedDocumentIds.length === 1
                    ? t("已选择 1 份资料")
                    : t("已选择 {count} 份资料", { count: selectedDocumentIds.length })
                  : readyDocuments.length === 1
                    ? t("搜索全部已就绪资料 · 1 份")
                    : t("搜索全部已就绪资料 · {count} 份", { count: readyDocuments.length })}
              </span>
            </div>

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
            {messagesLoading && (
              <p className="chat-loading" role="status">{t("正在整理你的对话…")}</p>
            )}
            {!messagesLoading && !messages.length && (
              <div className="chat-empty-state">
                <span className="chat-empty-mark" aria-hidden="true">✦</span>
                <h2>{readyDocuments.length ? t("你想从资料里了解什么？") : t("先准备一份学习资料")}</h2>
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
                {message.role === "user" ? (
                  <div className="chat-message-bubble">
                    <div className="chat-message-content">{message.content}</div>
                  </div>
                ) : (
                  <>
                    <div className="chat-message-content">{message.content}</div>
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
            {/* Materials are chosen from the composer, where the question is written. */}
            <button
              className="composer-plus"
              type="button"
              onClick={() => setShowScope((value) => !value)}
              aria-expanded={showScope}
              aria-label={t("选择资料")}
              disabled={!readyDocuments.length}
            >
              ＋
            </button>
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
    </main>
  );
}
