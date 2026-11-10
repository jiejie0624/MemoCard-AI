import { useCallback, useEffect, useMemo, useState } from "react";
import { apiUrl } from "../api.js";

const PENDING_REVIEW_KEY = "memocard.pending-review.v1";
const QUALITY_OPTIONS = [
  { quality: 0, label: "完全忘记" },
  { quality: 1, label: "几乎没想起" },
  { quality: 2, label: "想起一点" },
  { quality: 3, label: "很困难" },
  { quality: 4, label: "有些犹豫" },
  { quality: 5, label: "轻松记得" },
];

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method: options.method || "GET",
      credentials: "include",
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error("暂时无法连接复习服务，请检查网络后重试。");
  }

  let payload = null;
  try { payload = await response.json(); } catch { /* show the fallback below */ }
  if (!response.ok) {
    if (response.status === 409) throw new Error("这张卡已经不在待复习状态，请刷新列表后继续。");
    if (response.status === 401) throw new Error("登录状态已失效，请重新登录后再试。");
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "复习结果暂时无法保存，请重试。");
  }
  return payload;
}

function readPendingReview() {
  try {
    const value = sessionStorage.getItem(PENDING_REVIEW_KEY);
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

function makeIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  throw new Error("当前浏览器无法安全创建复习请求，请更新浏览器后重试。");
}

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "long" }).format(new Date(value));
}

export default function ReviewPage() {
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState("");
  const [pendingReview, setPendingReview] = useState(readPendingReview);
  const [submittingQuality, setSubmittingQuality] = useState(null);
  const [sessionTotal, setSessionTotal] = useState(0);

  const dueCards = useMemo(
    () => cards.filter((card) => new Date(card.next_review_at).getTime() <= Date.now()),
    [cards],
  );
  const currentCard = dueCards[0] || null;

  const loadCards = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const loaded = await request("/api/flashcards");
      setCards(loaded);
      setSessionTotal(loaded.filter((card) => new Date(card.next_review_at).getTime() <= Date.now()).length);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadCards(); }, [loadCards]);

  useEffect(() => {
    setRevealed(false);
    setError("");
  }, [currentCard?.id]);

  async function submitReview(quality) {
    if (!currentCard || !revealed || submittingQuality !== null) return;

    let requestState = pendingReview;
    if (!requestState || requestState.cardId !== currentCard.id) {
      try {
        requestState = { cardId: currentCard.id, key: makeIdempotencyKey(), quality };
        sessionStorage.setItem(PENDING_REVIEW_KEY, JSON.stringify(requestState));
        setPendingReview(requestState);
      } catch (requestError) {
        setError(requestError.message);
        return;
      }
    } else if (requestState.quality !== quality) {
      setError("上次评分尚未确认保存，请用相同评分重试，避免重复记账。");
      return;
    }

    setSubmittingQuality(quality);
    setError("");
    try {
      const result = await request(`/api/flashcards/${currentCard.id}/reviews`, {
        method: "POST",
        body: { quality, idempotency_key: requestState.key },
      });
      sessionStorage.removeItem(PENDING_REVIEW_KEY);
      setPendingReview(null);
      setCards((current) => current.map((card) => card.id === currentCard.id
        ? { ...card, next_review_at: result.next_review_at }
        : card));
      setRevealed(false);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmittingQuality(null);
    }
  }

  const pendingForCurrent = pendingReview?.cardId === currentCard?.id;

  return (
    <main className="review-page">
      <header className="review-page-heading">
        <div>
          <p className="eyebrow">MEMOCARD AI · 间隔复习</p>
          <h1>今日复习</h1>
          <p>先回想答案，再按记忆难度评分，系统会安排下一次复习。</p>
        </div>
        {!loading && !error && sessionTotal > 0 && (
          <div className="review-progress" aria-live="polite">
            <strong>{sessionTotal - dueCards.length + (currentCard ? 1 : 0)}</strong> / {sessionTotal} 张
          </div>
        )}
      </header>

      {error && (
        <div className="review-error" role="alert">
          <span>{error}</span>
          {error.includes("刷新列表") && <button className="text-button" type="button" onClick={loadCards}>刷新复习列表</button>}
        </div>
      )}
      {loading ? <p className="review-status" role="status">正在整理待复习卡片…</p> : error && !currentCard ? (
        <section className="review-empty">
          <h2>暂时无法加载复习内容</h2>
          <button className="secondary-button" type="button" onClick={loadCards}>重新加载</button>
        </section>
      ) : currentCard ? (
        <section className="review-session" aria-labelledby="review-question-title">
          <div className="review-session-meta">
            <span>第 {sessionTotal - dueCards.length + 1} 张</span>
            {currentCard.sources?.[0]?.document_name && <span>{currentCard.sources[0].document_name}</span>}
          </div>
          <article className="review-flashcard" aria-live="polite">
            <p className="eyebrow">{revealed ? "答案" : "问题"}</p>
            <h2 id="review-question-title">{revealed ? currentCard.answer : currentCard.question}</h2>
            {!revealed && <button className="primary-button" type="button" onClick={() => setRevealed(true)}>显示答案</button>}
          </article>

          {revealed && (
            <section className="review-rating" aria-labelledby="review-rating-title">
              <h3 id="review-rating-title">你记得怎么样？</h3>
              <p>0–2 表示没能回忆，3–5 表示答对；评分会调整下一次复习间隔。</p>
              <div className="review-quality-options">
                {QUALITY_OPTIONS.map(({ quality, label }) => {
                  const retryBlocked = pendingForCurrent && pendingReview.quality !== quality;
                  return (
                    <button
                      className="review-quality-button"
                      key={quality}
                      type="button"
                      disabled={submittingQuality !== null || retryBlocked}
                      aria-label={`${quality} 分：${label}`}
                      onClick={() => submitReview(quality)}
                    >
                      <strong>{quality}</strong>
                      <span>{submittingQuality === quality ? "保存中…" : pendingForCurrent && pendingReview.quality === quality ? "重试" : label}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}
        </section>
      ) : (
        <section className="review-empty">
          <span className="review-empty-mark" aria-hidden="true">✓</span>
          <h2>{cards.length ? "今天的复习完成了" : "还没有可复习的闪卡"}</h2>
          <p>{cards.length
            ? `全部完成。下一张卡片安排在 ${formatDate(cards.reduce((soonest, card) => new Date(card.next_review_at) < new Date(soonest.next_review_at) ? card : soonest).next_review_at)}。`
            : "先去 AI 问答中生成并保存闪卡，卡片到期后会出现在这里。"}</p>
          <button className="secondary-button" type="button" onClick={loadCards}>刷新复习列表</button>
        </section>
      )}
    </main>
  );
}
