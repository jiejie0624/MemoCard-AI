import { useCallback, useEffect, useMemo, useState } from "react";
import { apiUrl } from "../api.js";
import { useLanguage } from "../i18n.jsx";

const PENDING_REVIEW_KEY = "memocard.pending-review.v1";
// The binary verdict maps onto SM-2 without inventing a score: a recalled card is a
// "good" answer, a missed one restarts the sequence, and skipping counts as a failure.
const QUALITY_CORRECT = 4;
const QUALITY_PARTIAL = 3;
const QUALITY_WRONG = 2;

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method: options.method || "GET",
      credentials: "include",
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: AbortSignal.timeout(options.timeoutMs || 15000),
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

function formatDate(value, locale) {
  return new Intl.DateTimeFormat(locale, { dateStyle: "long" }).format(new Date(value));
}

export default function ReviewPage({ date = null }) {
  const { t, locale } = useLanguage();
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [revealed, setRevealed] = useState(false);
  // null = the card has not been checked yet; {correct: null} = the check failed and
  // the student makes the call instead.
  const [verdict, setVerdict] = useState(null);
  const [answerDraft, setAnswerDraft] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [pendingReview, setPendingReview] = useState(readPendingReview);
  const [submittingQuality, setSubmittingQuality] = useState(null);
  const [sessionTotal, setSessionTotal] = useState(0);
  const [lastScheduled, setLastScheduled] = useState("");
  // Practice walks the whole deck without touching the schedule: finishing today's due
  // cards should not be the end of the session for someone who wants to keep going.
  const [practice, setPractice] = useState(null);
  const [practiceRevealed, setPracticeRevealed] = useState(false);

  const dueCards = useMemo(() => {
    const due = cards.filter((card) => new Date(card.next_review_at).getTime() <= Date.now());
    if (!date) return due;
    // Opened from a calendar day: only that day's cards, so the date the student picked
    // and the cards they see agree.
    return due.filter((card) => {
      const value = new Date(card.next_review_at);
      const key = `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
      return key === date;
    });
  }, [cards, date]);
  const currentCard = dueCards[0] || null;
  // "Review today" also carries what is overdue — that is how spaced repetition keeps a
  // missed day from erasing the card. The page has to say so, or the extra cards look
  // like a bug, so the queue is split and each card is labelled with why it is here.
  const dayStart = useMemo(() => { const start = new Date(); start.setHours(0, 0, 0, 0); return start; }, []);
  const overdueCards = dueCards.filter((card) => new Date(card.next_review_at) < dayStart);
  const todayCards = dueCards.filter((card) => new Date(card.next_review_at) >= dayStart);
  const daysLate = (card) => Math.max(1, Math.ceil((dayStart - new Date(card.next_review_at)) / 86400000));

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
    setVerdict(null);
    setAnswerDraft("");
    setError("");
  }, [currentCard?.id]);

  async function checkAnswer(event) {
    event.preventDefault();
    const answer = answerDraft.trim();
    if (!currentCard || !answer || checking) return;
    setChecking(true);
    setError("");
    setLastScheduled("");
    try {
      const result = await request(`/api/flashcards/${currentCard.id}/answer-check`, {
        method: "POST",
        body: { answer },
        // The model needs a moment; keep it below the point where a retry feels stalled.
        timeoutMs: 30000,
      });
      setVerdict({ correct: result.correct === true, feedback: result.feedback || "" });
      setRevealed(true);
    } catch (requestError) {
      // Falling back to the student's own judgement keeps the review usable when the
      // provider is down; the answer is shown either way.
      setError(requestError.message);
      setVerdict({ correct: null, feedback: "" });
      setRevealed(true);
    } finally {
      setChecking(false);
    }
  }

  function skipToAnswer() {
    setVerdict({ correct: null, feedback: "" });
    setRevealed(true);
  }

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
      setError(t("上次评分尚未确认保存，请用相同评分重试，避免重复记账。"));
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
      // Telling the student when the card comes back is the only confirmation that the
      // rating actually changed the schedule; without it the card just disappears.
      setLastScheduled(formatDate(result.next_review_at, locale));
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
  const checkedQuality = verdict && verdict.correct !== null
    ? (verdict.correct ? QUALITY_CORRECT : QUALITY_WRONG)
    : null;
  const practiceCard = practice ? cards[practice.index] : null;

  if (practiceCard) {
    return (
      <main className="review-page">
        <header className="review-page-heading">
          <div>
            <p className="eyebrow">{t("MEMOCARD AI · 间隔复习")}</p>
            <h1>{t("练习模式")}</h1>
            <p>{t("练习不影响复习排期，随时可以退出。")}</p>
          </div>
          <button className="secondary-button" type="button" onClick={() => setPractice(null)}>
            {t("退出练习")}
          </button>
        </header>

        <section className="review-session">
          <div className="review-session-meta">
            <span>{t("第 {count} 张", { count: practice.index + 1 })} / {cards.length}</span>
            {practiceCard.sources?.[0]?.document_name && <span>{practiceCard.sources[0].document_name}</span>}
          </div>
          <article className="review-flashcard">
            <p className="eyebrow">{practiceRevealed ? t("参考答案") : t("问题")}</p>
            <h2>{practiceRevealed ? practiceCard.answer : practiceCard.question}</h2>
            {!practiceRevealed && (
              <button className="primary-button" type="button" onClick={() => setPracticeRevealed(true)}>
                {t("显示答案")}
              </button>
            )}
          </article>
          {practiceRevealed && (
            <div className="review-actions">
              <button className="secondary-button" type="button" onClick={() => setPractice(null)}>
                {t("退出练习")}
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => {
                  setPracticeRevealed(false);
                  const next = practice.index + 1;
                  setPractice(next < cards.length ? { index: next } : null);
                }}
              >
                {practice.index + 1 < cards.length ? t("下一张") : t("结束练习")}
              </button>
            </div>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="review-page">
      <header className="review-page-heading">
        <div>
          <p className="eyebrow">{t("MEMOCARD AI · 间隔复习")}</p>
          <h1>{t("今日复习")}</h1>
          <p>{t("先自己写下答案，再由 AI 判断是否答对；复习间隔会自动安排。")}</p>
        </div>
        {!loading && !error && dueCards.length > 0 && (
          <div className="review-progress" aria-live="polite">
            {overdueCards.length > 0 && (
              <>
                <strong>{overdueCards.length}</strong> {t("逾期")} <span aria-hidden="true">·</span>{" "}
              </>
            )}
            <strong>{todayCards.length}</strong> {t("今天到期")}
          </div>
        )}
      </header>

      {lastScheduled && (
        <p className="review-receipt" role="status">{t("已记录，下次复习：{date}", { date: lastScheduled })}</p>
      )}

      {error && (
        <div className="review-error" role="alert">
          <span>{t(error)}</span>
          {error.includes("刷新列表") && <button className="text-button" type="button" onClick={loadCards}>{t("刷新复习列表")}</button>}
        </div>
      )}
      {loading ? <p className="review-status" role="status">{t("正在整理待复习卡片…")}</p> : error && !currentCard ? (
        <section className="review-empty">
          <h2>{t("暂时无法加载复习内容")}</h2>
          <button className="secondary-button" type="button" onClick={loadCards}>{t("重新加载")}</button>
        </section>
      ) : currentCard ? (
        <section className="review-session" aria-labelledby="review-question-title">
          <div className="review-session-meta">
            <span>{t("第 {count} 张", { count: sessionTotal - dueCards.length + 1 })}</span>
            <span className={`review-due${new Date(currentCard.next_review_at) < dayStart ? " is-late" : ""}`}>
              {new Date(currentCard.next_review_at) < dayStart
                ? t("逾期 {days} 天", { days: daysLate(currentCard) })
                : t("今天到期")}
            </span>
            {currentCard.sources?.[0]?.document_name && <span>{currentCard.sources[0].document_name}</span>}
          </div>

          <article className="review-flashcard">
            <p className="eyebrow">{t("问题")}</p>
            <h2 id="review-question-title">{currentCard.question}</h2>

            {!revealed && (
              <form className="review-answer-form" onSubmit={checkAnswer}>
                <label>
                  <span>{t("写下你的答案")}</span>
                  <textarea
                    value={answerDraft}
                    onChange={(event) => setAnswerDraft(event.target.value)}
                    rows={3}
                    maxLength={5000}
                    placeholder={t("用一句话或几个要点回答")}
                    disabled={checking}
                  />
                </label>
                <div className="review-answer-actions">
                  <button className="text-button" type="button" onClick={skipToAnswer} disabled={checking}>
                    {t("不会，直接看答案")}
                  </button>
                  <button className="primary-button" type="submit" disabled={checking || !answerDraft.trim()}>
                    {checking ? t("正在检查…") : t("提交答案")}
                  </button>
                </div>
              </form>
            )}

            {revealed && (
              <div className="review-result">
                {verdict && verdict.correct !== null && (
                  <p className={`review-verdict ${verdict.correct ? "is-correct" : "is-wrong"}`} role="status">
                    <strong>{verdict.correct ? t("✓ 答对了") : t("✗ 还不对")}</strong>
                    {verdict.feedback && <span>{verdict.feedback}</span>}
                  </p>
                )}
                {verdict && verdict.correct === null && (
                  <p className="review-verdict is-unknown" role="status">{t("暂时无法自动判断，请看参考答案后自己选择。")}</p>
                )}
                <div className="review-reference">
                  <p className="eyebrow">{t("参考答案")}</p>
                  <p>{currentCard.answer}</p>
                </div>
              </div>
            )}
          </article>

          {revealed && (
            <div className="review-actions">
              {/* Three levels instead of two: "partly right" keeps a half-recalled card
                  from being scheduled exactly like a blank one. The AI verdict only
                  highlights a suggestion; the student always makes the final call. */}
              {(checkedQuality === null
                ? [
                    { quality: QUALITY_WRONG, label: t("我答错了") },
                    { quality: QUALITY_CORRECT, label: t("我答对了") },
                  ]
                : [{ quality: checkedQuality, label: t("下一张") }]
              ).map(({ quality, label }) => (
                <button
                  key={quality}
                  className={quality === checkedQuality ? "primary-button" : "secondary-button"}
                  type="button"
                  onClick={() => submitReview(quality)}
                  disabled={submittingQuality !== null}
                >
                  {submittingQuality === quality ? t("保存中…") : label}
                </button>
              ))}
              {pendingForCurrent && (
                <button
                  className="text-button"
                  type="button"
                  onClick={() => submitReview(pendingReview.quality)}
                  disabled={submittingQuality !== null}
                >
                  {t("重试上次评分")}
                </button>
              )}
            </div>
          )}
        </section>
      ) : (
        <section className="review-empty">
          <span className="review-empty-mark" aria-hidden="true">✓</span>
          <h2>{cards.length ? t("今天的复习完成了") : t("还没有可复习的闪卡")}</h2>
          <p>{cards.length
            ? t("全部完成。下一张卡片安排在 {date}。", { date: formatDate(cards.reduce((soonest, card) => new Date(card.next_review_at) < new Date(soonest.next_review_at) ? card : soonest).next_review_at, locale) })
            : t("先去 AI 问答中生成并保存闪卡，卡片到期后会出现在这里。")}</p>
          <button className="secondary-button" type="button" onClick={loadCards}>{t("刷新复习列表")}</button>
          {cards.length > 0 && (
            <button
              className="primary-button"
              type="button"
              onClick={() => { setPracticeRevealed(false); setPractice({ index: 0 }); }}
            >
              {t("再练一遍（不计入排期）")}
            </button>
          )}
        </section>
      )}
    </main>
  );
}
