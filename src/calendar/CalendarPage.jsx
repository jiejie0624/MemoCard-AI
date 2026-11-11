import { useCallback, useEffect, useMemo, useState } from "react";
import { apiUrl } from "../api.js";
import { useLanguage } from "../i18n.jsx";

async function request(path) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      credentials: "include",
      signal: AbortSignal.timeout(12000),
    });
  } catch {
    throw new Error("暂时无法连接日历服务，请检查网络后重试。");
  }
  let payload = null;
  try { payload = await response.json(); } catch { /* use fallback below */ }
  if (!response.ok) {
    if (response.status === 401) throw new Error("登录状态已失效，请重新登录后再试。");
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "日历暂时无法加载，请稍后重试。");
  }
  return payload;
}

function dateParts(value) {
  const [year, month, day] = value.split("-").map(Number);
  return { year, month, day };
}

function addDays(value, amount) {
  const { year, month, day } = dateParts(value);
  const date = new Date(Date.UTC(year, month - 1, day + amount));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

function visibleRange(month) {
  const { year, month: monthNumber } = dateParts(`${month}-01`);
  const first = new Date(Date.UTC(year, monthNumber - 1, 1));
  const mondayOffset = (first.getUTCDay() + 6) % 7;
  const start = addDays(`${month}-01`, -mondayOffset);
  return { start, end: addDays(start, 41) };
}

function shiftMonth(value, amount) {
  const { year, month } = dateParts(`${value}-01`);
  const shifted = new Date(Date.UTC(year, month - 1 + amount, 1));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}`;
}

function formatMonth(value, locale) {
  const { year, month } = dateParts(`${value}-01`);
  return new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", timeZone: "UTC" })
    .format(new Date(Date.UTC(year, month - 1, 1)));
}

export default function CalendarPage({ onStartReview }) {
  const { t, locale } = useLanguage();
  const [summary, setSummary] = useState(null);
  const [month, setMonth] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [days, setDays] = useState([]);
  const [dayCards, setDayCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [dayLoading, setDayLoading] = useState(false);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const range = useMemo(() => month ? visibleRange(month) : null, [month]);
  const counts = useMemo(() => new Map(days.map((item) => [item.date, item.count])), [days]);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await request("/api/dashboard/summary");
      setSummary(result);
      setMonth((current) => current || result.today.slice(0, 7));
      setSelectedDate((current) => current || result.today);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  useEffect(() => {
    if (!range) return;
    let cancelled = false;
    setCalendarLoading(true);
    request(`/api/revisions?from=${range.start}&to=${range.end}`)
      .then((result) => { if (!cancelled) { setDays(result.days); setError(""); } })
      .catch((requestError) => { if (!cancelled) setError(requestError.message); })
      .finally(() => { if (!cancelled) setCalendarLoading(false); });
    return () => { cancelled = true; };
  }, [range, refreshKey]);

  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    setDayLoading(true);
    request(`/api/revisions/day?date=${selectedDate}`)
      .then((result) => { if (!cancelled) { setDayCards(result.cards); setError(""); } })
      .catch((requestError) => { if (!cancelled) setError(requestError.message); })
      .finally(() => { if (!cancelled) setDayLoading(false); });
    return () => { cancelled = true; };
  }, [selectedDate, refreshKey]);

  const cells = useMemo(() => {
    if (!range) return [];
    return Array.from({ length: 42 }, (_, index) => {
      const value = addDays(range.start, index);
      return { value, day: dateParts(value).day, count: counts.get(value) || 0 };
    });
  }, [counts, range]);

  // A busy day can hold dozens of cards from several documents. Grouping by source keeps
  // the panel to one line per document, and everything starts collapsed so opening a day
  // never reveals the questions before the student has tried to recall them.
  const cardGroups = useMemo(() => {
    const groups = new Map();
    for (const card of dayCards) {
      const source = card.sources?.[0];
      const key = source?.id ?? "unsourced";
      if (!groups.has(key)) {
        groups.set(key, { key, name: source?.name ?? t("无来源的卡片"), cards: [] });
      }
      groups.get(key).cards.push(card);
    }
    return [...groups.values()];
  }, [dayCards, t]);

  function moveMonth(amount) {
    const nextMonth = shiftMonth(month, amount);
    setMonth(nextMonth);
    setSelectedDate(nextMonth === summary?.today.slice(0, 7) ? summary.today : `${nextMonth}-01`);
  }

  return (
    <main className="calendar-page">
      <header className="calendar-heading">
        <div>
          <p className="eyebrow">{t("MEMOCARD AI · 学习节奏")}</p>
          <h1>{t("复习日历")}</h1>
          <p>{t("按你的账号时区查看已安排的闪卡复习。")}</p>
        </div>
        {summary && (
          <div className="calendar-summary">
            <span><strong>{summary.overdue_count}</strong> {t("张逾期待复习")}</span>
            <span><strong>{summary.today_count}</strong> {t("张今天到期")}</span>
          </div>
        )}
      </header>

      {error && <div className="calendar-error" role="alert"><span>{t(error)}</span><button className="text-button" type="button" onClick={() => { setError(""); setRefreshKey((current) => current + 1); loadSummary(); }}>{t("重新加载")}</button></div>}
      {loading ? <p className="calendar-status" role="status">{t("正在加载复习日历…")}</p> : summary && (
        <div className="calendar-layout">
          <section className="calendar-panel" aria-label={t("复习日期")}>
            <div className="calendar-month-heading">
              <button className="calendar-month-button" type="button" aria-label={t("上一个月")} onClick={() => moveMonth(-1)}>‹</button>
              <h2>{formatMonth(month, locale)}</h2>
              <button className="calendar-month-button" type="button" aria-label={t("下一个月")} onClick={() => moveMonth(1)}>›</button>
            </div>
            <div className="calendar-grid calendar-weekdays" aria-hidden="true">
              {["一", "二", "三", "四", "五", "六", "日"].map((day) => <span key={day}>{t(day)}</span>)}
            </div>
            <div className="calendar-grid calendar-days" aria-busy={calendarLoading}>
              {cells.map((cell) => (
                <button
                  className={`calendar-day${cell.value.slice(0, 7) !== month ? " is-outside" : ""}${cell.value === selectedDate ? " is-selected" : ""}${cell.value === summary.today ? " is-today" : ""}`}
                  key={cell.value}
                  type="button"
                  aria-label={t("{date}，{count} 张待复习", { date: cell.value, count: cell.count })}
                  aria-pressed={cell.value === selectedDate}
                  onClick={() => {
                    if (cell.value.slice(0, 7) !== month) setMonth(cell.value.slice(0, 7));
                    setSelectedDate(cell.value);
                  }}
                >
                  <span>{cell.day}</span>
                  {cell.count > 0 && <small>{cell.count}</small>}
                </button>
              ))}
            </div>
            <div className="calendar-legend"><span aria-hidden="true" /> {t("有待复习卡片")}</div>
          </section>

          <aside className="calendar-day-panel" aria-live="polite">
            <div className="calendar-day-heading">
              <div><p className="eyebrow">{t("所选日期")}</p><h2>{selectedDate}</h2></div>
              {selectedDate <= summary.today && dayCards.length > 0 && (
                <button className="primary-button" type="button" onClick={() => onStartReview(selectedDate)}>{t("开始复习")}</button>
              )}
            </div>
            {dayLoading ? <p className="calendar-status">{t("正在加载当天卡片…")}</p> : dayCards.length ? (
              <div className="calendar-card-list">
                {cardGroups.map((group) => (
                  <details className="calendar-group" key={group.key}>
                    <summary>
                      <span className="calendar-group-name">{group.name}</span>
                      <span className="calendar-group-count">{t("{count} 张", { count: group.cards.length })}</span>
                    </summary>
                    <ul className="calendar-group-cards">
                      {group.cards.map((card, index) => (
                        <li key={card.id}>
                          <details className="calendar-card-item">
                            <summary>{t("第 {count} 张", { count: index + 1 })}</summary>
                            <h3>{card.question}</h3>
                          </details>
                        </li>
                      ))}
                    </ul>
                  </details>
                ))}
              </div>
            ) : <p className="calendar-no-cards">{t("这一天没有安排复习。")}</p>}
          </aside>
        </div>
      )}
    </main>
  );
}
