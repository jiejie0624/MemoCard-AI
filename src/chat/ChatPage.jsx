import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "../api.js";

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

function formatSessionTitle(session) {
  return session.title || "新对话";
}

function CitationList({ citations }) {
  if (!citations?.length) return null;
  return (
    <details className="chat-citations">
      <summary>查看 {citations.length} 个资料来源</summary>
      <ol>
        {citations.map((citation) => (
          <li key={`${citation.rank}-${citation.document_name}-${citation.page_number}-${citation.slide_number}`}>
            <strong>{citation.document_name}</strong>
            {(citation.page_number || citation.slide_number) && (
              <span>{citation.page_number ? ` · 第 ${citation.page_number} 页` : ` · 第 ${citation.slide_number} 张`}</span>
            )}
            <p>{citation.excerpt}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

export default function ChatPage({ onOpenDocuments, onOpenFlashcards }) {
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
  const bottomRef = useRef(null);

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
    return <main className="chat-page"><p className="chat-loading" role="status">正在整理你的对话…</p></main>;
  }

  return (
    <main className="chat-page">
      <header className="chat-page-heading">
        <div>
          <p className="eyebrow">MEMOCARD AI · 学习问答</p>
          <h1>AI 问答</h1>
          <p>结合已处理的课程资料回答，并附上可核对的来源。</p>
        </div>
        <button className="primary-button chat-new-button" type="button" onClick={startNewSession}>
          新建对话
        </button>
      </header>

      <section className="chat-workspace" aria-label="AI 问答工作区">
        <aside className="chat-session-list" aria-label="对话历史">
          <div className="chat-session-list-heading">
            <h2>对话</h2>
            <span>{sessions.length}</span>
          </div>
          {sessions.length ? sessions.map((session) => (
            <button
              className={`chat-session-item${activeSession?.id === session.id ? " is-active" : ""}`}
              type="button"
              key={session.id}
              onClick={() => openSession(session)}
            >
              <strong>{formatSessionTitle(session)}</strong>
              <span>{session.message_count || 0} 条消息</span>
            </button>
          )) : <p className="chat-session-empty">发送第一个问题后，对话会显示在这里。</p>}
        </aside>

        <div className="chat-thread">
          <div className="chat-thread-topline">
            <div>
              <strong>{activeSession ? formatSessionTitle(activeSession) : "开始一个新对话"}</strong>
              <span>
                {activeSession?.all_documents === false
                  ? `已选择 ${selectedDocumentIds.length} 份资料`
                  : `搜索全部已就绪资料 · ${readyDocuments.length} 份`}
              </span>
            </div>
            {!activeSession && (
              <button className="text-button" type="button" onClick={() => setShowScope((value) => !value)}>
                {showScope ? "收起资料选择" : "选择资料"}
              </button>
            )}
          </div>

          {showScope && !activeSession && (
            <div className="chat-scope-panel" aria-label="选择本次对话资料">
              <p>默认搜索全部已就绪资料。勾选后，只搜索选中的资料。</p>
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
                  恢复搜索全部资料
                </button>
              )}
            </div>
          )}

          <div className="chat-message-list" aria-live="polite">
            {!messages.length && (
              <div className="chat-empty-state">
                <span className="chat-empty-mark" aria-hidden="true">✦</span>
                <h2>{readyDocuments.length ? "你想从资料里了解什么？" : "先准备一份学习资料"}</h2>
                <p>
                  {readyDocuments.length
                    ? "我会先查找相关内容，再根据找到的片段回答并标出来源。"
                    : "上传并处理 PDF、TXT 或 PPTX 后，就可以针对内容提问。"}
                </p>
                {!readyDocuments.length && (
                  <button className="secondary-button" type="button" onClick={onOpenDocuments}>
                    前往学习资料
                  </button>
                )}
              </div>
            )}
            {messages.map((message) => (
              <article className={`chat-message chat-message-${message.role}`} key={message.id}>
                <div className="chat-message-label">{message.role === "user" ? "你" : "MemoCard AI"}</div>
                <div className="chat-message-content">{message.content}</div>
                {message.role === "assistant" && (
                  <>
                    <CitationList citations={message.citations} />
                    {message.citations?.length > 0 && (
                      <button className="text-button chat-generate-cards" type="button"
                        onClick={() => generateCards(message)}>
                        生成闪卡
                      </button>
                    )}
                  </>
                )}
              </article>
            ))}
            {sending && <p className="chat-thinking" role="status">正在查找资料并整理回答…</p>}
            <div ref={bottomRef} />
          </div>

          {error && <p className="chat-error" role="alert">{error}</p>}
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
              placeholder={readyDocuments.length ? "输入关于课程资料的问题…" : "处理好学习资料后即可提问"}
              disabled={!readyDocuments.length || sending}
              aria-label="输入问题"
            />
            <button className="primary-button" type="submit" disabled={!question.trim() || sending || !readyDocuments.length}>
              {sending ? "回答中…" : "发送"}
            </button>
            <span>Enter 发送 · Shift + Enter 换行</span>
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
                <p className="eyebrow">来自 AI 回答</p>
                <h2 id="flashcard-draft-title">检查闪卡草稿</h2>
              </div>
              <button type="button" className="dialog-close" aria-label="关闭闪卡草稿"
                onClick={() => setDraftSource(null)} disabled={savingDraft || generatingDraft}>×</button>
            </header>
            <div className="flashcard-draft-body">
              {generatingDraft ? <p className="chat-thinking" role="status">正在根据回答和引用整理闪卡…</p> : (
                <>
                  {draftCards.map((card, index) => (
                    <article className="flashcard-draft-item" key={`${index}-${card.question}`}>
                      <div className="flashcard-draft-item-heading">
                        <strong>卡片 {index + 1}</strong>
                        <button className="text-button is-danger" type="button"
                          onClick={() => setDraftCards((current) => current.filter((_, cardIndex) => cardIndex !== index))}>
                          移除此卡
                        </button>
                      </div>
                      <label><span>问题</span><textarea value={card.question} maxLength={2000}
                        onChange={(event) => updateDraft(index, "question", event.target.value)} /></label>
                      <label><span>答案</span><textarea value={card.answer} maxLength={5000}
                        onChange={(event) => updateDraft(index, "answer", event.target.value)} /></label>
                      <span className="flashcard-draft-source">引用来源：{card.source_refs.map((rank) => `来源 ${rank}`).join("、")}</span>
                    </article>
                  ))}
                  {!draftCards.length && !draftError && <p className="chat-session-empty">没有可保存的草稿。</p>}
                </>
              )}
              {draftError && <p className="chat-error" role="alert">{draftError}</p>}
            </div>
            <footer>
              <button className="cancel-button" type="button" onClick={() => setDraftSource(null)} disabled={savingDraft}>取消</button>
              {!generatingDraft && draftError && !draftCards.length && (
                <button className="secondary-button" type="button" onClick={() => generateCards(draftSource)} disabled={savingDraft}>重试生成</button>
              )}
              <button className="primary-button" type="button" onClick={saveDraftCards}
                disabled={generatingDraft || savingDraft || !draftCards.length}>
                {savingDraft ? "正在保存…" : `保存 ${draftCards.length} 张闪卡`}
              </button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}
