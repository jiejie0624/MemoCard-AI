import { useCallback, useEffect, useState } from "react";
import { apiUrl } from "../api.js";
import { useLanguage } from "../i18n.jsx";

// Layout follows the common analytics hierarchy: one hero metric, then proportions, then
// a time trend. Everything is plain SVG/CSS, so no chart library enters the bundle.

async function requestSummary() {
  let response;
  try {
    response = await fetch(apiUrl("/api/analytics/summary"), {
      credentials: "include",
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error("无法连接学习数据服务，请检查网络后重试。");
  }
  let payload = null;
  try { payload = await response.json(); } catch { /* use the fallback below */ }
  if (!response.ok) {
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "学习数据暂时无法加载。");
  }
  return payload;
}

// The API returns plain dates, so they are parsed as UTC midnight and formatted in
// UTC: converting through the browser's zone would shift the label to the day before.
function formatDay(value, locale) {
  return new Intl.DateTimeFormat(locale, { month: "numeric", day: "numeric", timeZone: "UTC" })
    .format(new Date(`${value}T00:00:00Z`));
}

function todayInZone(timezone) {
  // en-CA formats as YYYY-MM-DD, which matches the API's date strings.
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone }).format(new Date());
}

function AccuracyRing({ rate }) {
  const size = 88;
  const stroke = 8;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const value = rate === null ? 0 : Math.min(1, Math.max(0, rate));
  return (
    <svg className="analytics-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#eef2f8" strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#2878e3"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${circumference * value} ${circumference}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}

export default function AnalyticsPage() {
  const { t, locale } = useLanguage();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSummary(await requestSummary());
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  const mastery = summary ? [
    { key: "learning", label: t("学习中"), value: summary.mastery.learning },
    { key: "mastered", label: t("已掌握"), value: summary.mastery.mastered },
    { key: "new", label: t("新卡"), value: summary.mastery.new },
  ] : [];
  const masteryTotal = mastery.reduce((sum, row) => sum + row.value, 0);
  const upcomingMax = Math.max(1, ...(summary?.upcoming ?? []).map((day) => day.count));
  const today = summary ? todayInZone(summary.timezone) : "";
  const streakDots = Math.min(summary?.streak_days ?? 0, 7);
  // Seven points is too few for a bar chart and just right for a sparkline: the shape
  // answers "how heavy is the week" faster than seven separate columns.
  const upcoming = summary?.upcoming ?? [];
  const sparkPoints = upcoming.map((day, index) => ({
    ...day,
    x: upcoming.length > 1 ? (index / (upcoming.length - 1)) * 100 : 50,
    y: 34 - (day.count / upcomingMax) * 28,
  }));
  const sparkLine = sparkPoints.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
  const sparkArea = `0,40 ${sparkLine} 100,40`;

  return (
    <main className="analytics-page">
      <header className="analytics-heading">
        <div>
          <p className="eyebrow">{t("MEMOCARD AI · 学习数据")}</p>
          <h1>{t("学习数据")}</h1>
          <p>{t("查看正确率、卡片掌握程度和未来七天的复习负荷。")}</p>
        </div>
      </header>

      {error && (
        <div className="analytics-error" role="alert">
          <span>{t(error)}</span>
          <button className="text-button" type="button" onClick={loadSummary}>{t("重新加载")}</button>
        </div>
      )}

      {loading ? (
        <p className="analytics-status" role="status">{t("正在汇总学习数据…")}</p>
      ) : summary && (
        <>
          <section className="analytics-hero" aria-label={t("学习概览")}>
            <div className="analytics-metric">
              <span className="analytics-label">{t("连续复习")}</span>
              <p className="analytics-value">
                {summary.streak_days}<span className="analytics-unit">{t(summary.streak_days === 1 ? "天_1" : "天")}</span>
              </p>
              <span className="analytics-dots" aria-hidden="true">
                {Array.from({ length: 7 }, (_, index) => (
                  <i key={index} className={index < streakDots ? "is-on" : ""} />
                ))}
              </span>
            </div>

            <div className="analytics-metric">
              <span className="analytics-label">{t("正确率")}</span>
              <span className="analytics-ring-wrap">
                <AccuracyRing rate={summary.correct_rate} />
                <strong>{summary.correct_rate === null ? "—" : `${Math.round(summary.correct_rate * 100)}%`}</strong>
              </span>
            </div>

            <div className="analytics-metric">
              <span className="analytics-label">{t("次复习")}</span>
              <p className="analytics-value">{summary.reviewed_total}</p>
            </div>
          </section>

          {summary.correct_rate === null && (
            <p className="analytics-hint">
              {summary.reviewed_total === 0
                ? t("还没有复习记录，复习几次后这里会显示正确率。")
                : t("复习满 5 次后开始显示正确率。")}
            </p>
          )}

          <section className="analytics-section" aria-labelledby="analytics-mastery-title">
            <div className="analytics-section-heading">
              <h2 id="analytics-mastery-title">{t("掌握程度")}</h2>
              <span>{t("共 {count} 张", { count: masteryTotal })}</span>
            </div>
            {masteryTotal > 0 ? (
              <>
                <div className="analytics-stack" aria-hidden="true">
                  {mastery.map((row) => (
                    <span
                      key={row.key}
                      className={`analytics-stack-seg is-${row.key}`}
                      style={{ flexGrow: row.value }}
                    />
                  ))}
                </div>
                <ul className="analytics-legend">
                  {mastery.map((row) => (
                    <li key={row.key}>
                      <i className={`is-${row.key}`} aria-hidden="true" />
                      {row.label}
                      <strong>{row.value}</strong>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="analytics-empty">{t("保存闪卡后，这里会显示掌握程度。")}</p>
            )}
          </section>

          <section className="analytics-section" aria-labelledby="analytics-load-title">
            <div className="analytics-section-heading">
              <h2 id="analytics-load-title">{t("未来 7 天复习负荷")}</h2>
            </div>
            {summary.upcoming.length ? (
              <div className="analytics-spark">
                
                <div className="analytics-week">
                  {sparkPoints.map((point) => (
                    <span key={point.date} className={point.date === today ? "is-today" : ""}>
                      <strong>{point.count}</strong>
                      {formatDay(point.date, locale)}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <p className="analytics-empty">{t("接下来 7 天没有安排复习。")}</p>
            )}
          </section>
        </>
      )}
    </main>
  );
}
