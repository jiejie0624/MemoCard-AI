import { useCallback, useEffect, useState } from "react";
import { apiUrl } from "../api.js";
import { useLanguage } from "../i18n.jsx";

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

function Bar({ label, value, percent }) {
  return (
    <li>
      <span className="analytics-bar-label">{label}</span>
      <span className="analytics-bar-track" aria-hidden="true">
        <span className="analytics-bar-fill" style={{ width: `${percent}%` }} />
      </span>
      <span className="analytics-bar-value">{value}</span>
    </li>
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

  const masteryRows = summary ? [
    { key: "new", label: t("新卡"), value: summary.mastery.new },
    { key: "learning", label: t("学习中"), value: summary.mastery.learning },
    { key: "mastered", label: t("已掌握"), value: summary.mastery.mastered },
  ] : [];
  const masteryMax = Math.max(1, ...masteryRows.map((row) => row.value));
  const upcomingMax = Math.max(1, ...(summary?.upcoming ?? []).map((day) => day.count));

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
          <section className="analytics-overview" aria-label={t("学习概览")}>
            <div>
              <strong>{summary.reviewed_total}</strong>
              <span>{t("次复习")}</span>
            </div>
            <div>
              <strong>{summary.correct_rate === null ? "—" : `${Math.round(summary.correct_rate * 100)}%`}</strong>
              <span>{t("正确率")}</span>
            </div>
            <div>
              <strong>{summary.streak_days}</strong>
              <span>{t("天连续复习")}</span>
            </div>
          </section>

          {summary.reviewed_total > 0 && summary.correct_rate === null && (
            <p className="analytics-hint">{t("复习满 5 次后开始显示正确率。")}</p>
          )}

          <section className="analytics-section" aria-labelledby="analytics-mastery-title">
            <h2 id="analytics-mastery-title">{t("掌握程度")}</h2>
            <ul className="analytics-bars">
              {masteryRows.map((row) => (
                <Bar
                  key={row.key}
                  label={row.label}
                  value={row.value}
                  percent={Math.round((row.value / masteryMax) * 100)}
                />
              ))}
            </ul>
          </section>

          <section className="analytics-section" aria-labelledby="analytics-load-title">
            <h2 id="analytics-load-title">{t("未来 7 天复习负荷")}</h2>
            {summary.upcoming.length ? (
              <ul className="analytics-bars">
                {summary.upcoming.map((day) => (
                  <Bar
                    key={day.date}
                    label={formatDay(day.date, locale)}
                    value={day.count}
                    percent={Math.round((day.count / upcomingMax) * 100)}
                  />
                ))}
              </ul>
            ) : (
              <p className="analytics-empty">{t("接下来 7 天没有安排复习。")}</p>
            )}
          </section>
        </>
      )}
    </main>
  );
}
