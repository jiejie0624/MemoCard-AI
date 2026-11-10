import { useEffect, useRef, useState } from "react";
import { apiUrl } from "./api.js";
import ChatPage from "./chat/ChatPage.jsx";
import CalendarPage from "./calendar/CalendarPage.jsx";
import DocumentsPage from "./documents/DocumentsPage.jsx";
import FlashcardsPage from "./flashcards/FlashcardsPage.jsx";
import ReviewPage from "./review/ReviewPage.jsx";
import "./styles.css";

const AUTH_API = "/api/auth";

function getBrowserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function errorMessage(payload, status, path) {
  const detail = payload?.detail;
  if (status === 409) return "这个邮箱已经注册过了，请直接登录。";
  if (status === 401 && path === "/login") return "邮箱或密码不正确，请检查后再试。";
  if (status === 401) return "登录状态已失效，请重新登录后再试。";
  if (status === 422) {
    const firstError = Array.isArray(detail) ? detail[0] : null;
    if (firstError?.loc?.includes("password")) return "密码至少需要 12 个字符。";
    if (firstError?.loc?.includes("display_name")) return "请填写你的姓名。";
    if (firstError?.loc?.includes("email")) return "请输入有效的邮箱地址。";
    if (firstError?.loc?.includes("timezone")) return "请填写有效时区，例如 Asia/Kuala_Lumpur。";
    return "请检查填写的内容后再试。";
  }
  if (status >= 500 && !payload) {
    return "无法连接认证服务。请确认 FastAPI 正在运行，并检查本地数据库配置。";
  }
  if (status >= 500) return "认证服务暂时无法完成请求，请稍后再试。";
  if (typeof detail === "string" && detail.length < 160) return detail;
  return "暂时无法完成请求，请稍后再试。";
}

async function requestAuth(path, { method = "GET", body } = {}) {
  let response;
  try {
    response = await fetch(apiUrl(`${AUTH_API}${path}`), {
      method,
      credentials: "include",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(12000),
    });
  } catch {
    throw new ApiError("无法连接认证服务。请确认 FastAPI 正在运行，并检查本地数据库配置。", 0);
  }

  if (response.status === 204) return null;

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // A non-JSON error response is shown as a short, user-friendly message below.
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(payload, response.status, path), response.status);
  }
  return payload;
}

async function requestDashboardSummary() {
  const response = await fetch(apiUrl("/api/dashboard/summary"), {
    credentials: "include",
    signal: AbortSignal.timeout(12000),
  });
  let payload = null;
  try { payload = await response.json(); } catch { /* use a friendly fallback */ }
  if (!response.ok) {
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "学习摘要暂时无法加载。");
  }
  return payload;
}

function formatReviewDate(value, timezone) {
  if (!value) return "暂无安排";
  return new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", timeZone: timezone }).format(new Date(value));
}

function Brand({ compact = false }) {
  return (
    <div className={`brand-lockup${compact ? " brand-lockup-compact" : ""}`}>
      <span className="brand-mark" aria-hidden="true">M</span>
      <span className="brand-name">MemoCard AI</span>
    </div>
  );
}

function AuthPage({ onAuthenticated, connectionNotice }) {
  const [mode, setMode] = useState("login");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const isRegistering = mode === "register";

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    const values = Object.fromEntries(new FormData(event.currentTarget));
    const payload = {
      email: values.email,
      password: values.password,
      ...(isRegistering
        ? { display_name: values.display_name, timezone: getBrowserTimezone() }
        : {}),
    };

    try {
      const user = await requestAuth(isRegistering ? "/register" : "/login", {
        method: "POST",
        body: payload,
      });
      onAuthenticated(user);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  function changeMode(nextMode) {
    setMode(nextMode);
    setError("");
    setShowPassword(false);
  }

  return (
    <main className="auth-stage">
      <section className="auth-card" aria-label="MemoCard AI 账号">
        <aside className="auth-story">
          <div className="story-decoration story-decoration-one" aria-hidden="true" />
          <div className="story-decoration story-decoration-two" aria-hidden="true" />
          <Brand />
          <div className="story-copy">
            <p className="eyebrow story-eyebrow">PERSONAL LEARNING WORKSPACE</p>
            <h1>把每一份资料，<br />变成长期记忆。</h1>
            <p className="story-description">
              从课程资料出发，整理知识、提出问题，再慢慢建立适合自己的复习节奏。
            </p>
          </div>
          <div className="story-footer">
            <span className="story-footer-dot" aria-hidden="true" />
            <span>给学习留一点持续向前的空间</span>
          </div>
        </aside>

        <section className="auth-panel">
          <div className="auth-form-wrap" key={mode}>
            <p className="eyebrow auth-eyebrow">欢迎来到你的学习空间</p>
            <h2>{isRegistering ? "创建账号" : "欢迎回来"}</h2>
            <p className="form-intro">
              {isRegistering ? "建立账号，开始整理你的学习内容。" : "登录后继续你的学习计划。"}
            </p>

            <div className="auth-tabs" role="group" aria-label="登录或注册">
              <button
                type="button"
                aria-pressed={!isRegistering}
                className={!isRegistering ? "auth-tab is-active" : "auth-tab"}
                disabled={submitting}
                onClick={() => changeMode("login")}
              >
                登录
              </button>
              <button
                type="button"
                aria-pressed={isRegistering}
                className={isRegistering ? "auth-tab is-active" : "auth-tab"}
                disabled={submitting}
                onClick={() => changeMode("register")}
              >
                注册
              </button>
            </div>

            {connectionNotice && !error && (
              <p className="form-notice" role="status">{connectionNotice}</p>
            )}

            <form className="auth-form" onSubmit={handleSubmit}>
              {isRegistering && (
                <label className="field-group">
                  <span>姓名</span>
                  <input
                    name="display_name"
                    type="text"
                    autoComplete="name"
                    placeholder="你希望我们怎么称呼你"
                    minLength={1}
                    maxLength={100}
                    required
                  />
                </label>
              )}

              <label className="field-group">
                <span>邮箱</span>
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="name@example.com"
                  maxLength={320}
                  required
                />
              </label>

              <label className="field-group">
                <span>密码</span>
                <span className="password-field">
                  <input
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete={isRegistering ? "new-password" : "current-password"}
                    placeholder={isRegistering ? "至少 12 个字符" : "请输入你的密码"}
                    minLength={12}
                    maxLength={1024}
                    required
                  />
                  <button
                    className="password-toggle"
                    type="button"
                    aria-label={showPassword ? "隐藏密码" : "显示密码"}
                    onClick={() => setShowPassword((current) => !current)}
                  >
                    {showPassword ? "隐藏" : "显示"}
                  </button>
                </span>
              </label>

              {error && <p className="form-error" role="alert">{error}</p>}

              <button className="primary-button auth-submit" type="submit" disabled={submitting}>
                {submitting ? "请稍候…" : isRegistering ? "创建账号" : "登录"}
                {!submitting && <span aria-hidden="true">→</span>}
              </button>
            </form>

            <p className="auth-footnote">
              注册或登录即开始使用 MemoCard AI 学习工作台。
            </p>
          </div>
        </section>
      </section>
    </main>
  );
}

function Dashboard({ user, onUserUpdated, onLoggedOut }) {
  const profileDialog = useRef(null);
  const [activeSection, setActiveSection] = useState("home");
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState("");
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileName, setProfileName] = useState(user.display_name || "");
  const [profileTimezone, setProfileTimezone] = useState(user.timezone || "UTC");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryRefreshKey, setSummaryRefreshKey] = useState(0);
  const displayName = user.display_name || user.email;
  const initials = displayName.trim().slice(0, 1).toUpperCase();

  useEffect(() => {
    if (activeSection !== "home") return undefined;
    let cancelled = false;
    setSummaryLoading(true);
    setSummaryError("");
    requestDashboardSummary()
      .then((result) => { if (!cancelled) setSummary(result); })
      .catch((requestError) => { if (!cancelled) setSummaryError(requestError.message); })
      .finally(() => { if (!cancelled) setSummaryLoading(false); });
    return () => { cancelled = true; };
  }, [activeSection, summaryRefreshKey]);

  useEffect(() => {
    const dialog = profileDialog.current;
    if (!dialog) return;
    if (editingProfile && !dialog.open) dialog.showModal();
    if (!editingProfile && dialog.open) dialog.close();
  }, [editingProfile]);

  function openProfile() {
    setProfileName(user.display_name || "");
    setProfileTimezone(user.timezone || getBrowserTimezone());
    setProfileError("");
    setEditingProfile(true);
  }

  async function handleProfileSubmit(event) {
    event.preventDefault();
    const display_name = profileName.trim();
    const timezone = profileTimezone.trim();
    if (!display_name) {
      setProfileError("姓名不能为空。");
      return;
    }
    if (!timezone) {
      setProfileError("请填写有效的时区，例如 Asia/Kuala_Lumpur。");
      return;
    }

    setSavingProfile(true);
    setProfileError("");
    try {
      const updatedUser = await requestAuth("/me", {
        method: "PATCH",
        body: { display_name, timezone },
      });
      onUserUpdated(updatedUser);
      setEditingProfile(false);
    } catch (requestError) {
      setProfileError(requestError.message);
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleLogout() {
    setSigningOut(true);
    setError("");
    try {
      await requestAuth("/logout", { method: "POST" });
      onLoggedOut();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="workspace-shell">
      <aside className="sidebar">
        <div className="sidebar-top">
          <Brand compact />
          <div className="workspace-label">学习工作台</div>
          <nav className="primary-nav" aria-label="主导航">
            <button
              className={`nav-item${activeSection === "home" ? " is-current" : ""}`}
              type="button"
              aria-current={activeSection === "home" ? "page" : undefined}
              onClick={() => setActiveSection("home")}
            >
              <span className="nav-indicator" aria-hidden="true" />
              首页
            </button>
            <button
              className={`nav-item${activeSection === "documents" ? " is-current" : ""}`}
              type="button"
              aria-current={activeSection === "documents" ? "page" : undefined}
              onClick={() => setActiveSection("documents")}
            >
              <span className="nav-indicator" aria-hidden="true" />
              学习资料
            </button>
            <button
              className={`nav-item${activeSection === "chat" ? " is-current" : ""}`}
              type="button"
              aria-current={activeSection === "chat" ? "page" : undefined}
              onClick={() => setActiveSection("chat")}
            >
              <span className="nav-indicator" aria-hidden="true" />
              AI 问答
            </button>
            <button
              className={`nav-item${activeSection === "flashcards" ? " is-current" : ""}`}
              type="button"
              aria-current={activeSection === "flashcards" ? "page" : undefined}
              onClick={() => setActiveSection("flashcards")}
            >
              <span className="nav-indicator" aria-hidden="true" />
              闪卡
            </button>
            <button
              className={`nav-item${activeSection === "review" ? " is-current" : ""}`}
              type="button"
              aria-current={activeSection === "review" ? "page" : undefined}
              onClick={() => setActiveSection("review")}
            >
              <span className="nav-indicator" aria-hidden="true" />
              今日复习
            </button>
            <button
              className={`nav-item${activeSection === "calendar" ? " is-current" : ""}`}
              type="button"
              aria-current={activeSection === "calendar" ? "page" : undefined}
              onClick={() => setActiveSection("calendar")}
            >
              <span className="nav-indicator" aria-hidden="true" />
              复习日历
            </button>
          </nav>
        </div>

        <div className="sidebar-account">
          <span className="account-avatar" aria-hidden="true">{initials}</span>
          <button className="account-details profile-trigger" type="button" onClick={openProfile} aria-label="编辑个人资料">
            <strong>{displayName}</strong>
            <span>{user.email}</span>
            <span className="profile-trigger-hint">编辑个人资料</span>
          </button>
          <button
            className="logout-button"
            type="button"
            onClick={handleLogout}
            disabled={signingOut}
            aria-label="退出登录"
            title="退出登录"
          >
            {signingOut ? "…" : "↗"}
          </button>
        </div>
      </aside>

      <main className="workspace-main">
        {error && <p className="dashboard-error" role="alert">{error}</p>}
        {activeSection === "documents" ? <DocumentsPage /> : activeSection === "chat" ? (
          <ChatPage
            onOpenDocuments={() => setActiveSection("documents")}
            onOpenFlashcards={() => setActiveSection("flashcards")}
          />
        ) : activeSection === "flashcards" ? (
          <FlashcardsPage />
        ) : activeSection === "review" ? (
          <ReviewPage />
        ) : activeSection === "calendar" ? (
          <CalendarPage onStartReview={() => setActiveSection("review")} />
        ) : (
        <div className="workspace-content">
          <header className="dashboard-heading">
            <div>
              <p className="eyebrow">MEMOCARD AI · 学习空间</p>
              <h1>你好，{displayName}</h1>
              <p className="dashboard-subtitle">把今天学到的内容，慢慢变成自己的知识。</p>
            </div>
            <span className="workspace-status">
              <span className="status-dot" aria-hidden="true" />
              个人空间
            </span>
          </header>

          <section className="review-card" aria-labelledby="review-card-title">
            <div className="review-copy">
              <p className="eyebrow review-eyebrow">今日学习</p>
              <h2 id="review-card-title">继续今天的复习</h2>
              <p>
                {summaryLoading ? "正在读取你的复习安排…" : summaryError
                  ? "暂时无法读取复习安排，请重试或打开复习日历。"
                  : `逾期 ${summary?.overdue_count ?? 0} 张 · 今天 ${summary?.today_count ?? 0} 张 · 未来 7 天 ${summary?.upcoming_count ?? 0} 张`}
              </p>
              {summaryError ? (
                <button className="secondary-button" type="button" onClick={() => setActiveSection("calendar")}>
                  查看复习日历
                </button>
              ) : (
                <button className="secondary-button" type="button" onClick={() => setActiveSection("review")} disabled={summaryLoading}>
                  {(summary?.overdue_count || summary?.today_count) ? "开始复习" : "查看复习安排"}
                </button>
              )}
              {summary?.next_review_at && !summaryLoading && (
                <span className="dashboard-next-review">下一张：{formatReviewDate(summary.next_review_at, summary.timezone)}</span>
              )}
              {summaryError && <button className="text-button" type="button" onClick={() => setSummaryRefreshKey((current) => current + 1)}>重新加载</button>}
              <button className="text-button" type="button" onClick={() => setActiveSection("calendar")}>
                打开复习日历 <span aria-hidden="true">→</span>
              </button>
            </div>
            <div className="review-art" aria-label="布里布里左卫门手绘图">
              <img
                src="/images/buriburi-review.png"
                alt="你提供的布里布里左卫门手绘图"
                width="262"
                height="345"
              />
            </div>
          </section>

          <section className="workspace-note" aria-labelledby="workspace-note-title">
            <div className="note-mark" aria-hidden="true">✦</div>
            <div>
              <h2 id="workspace-note-title">学习资料入口已开放</h2>
              <p>资料上传、AI 问答、闪卡管理、间隔复习和复习日历都已接入。</p>
              <button className="text-button home-documents-link" type="button" onClick={() => setActiveSection("documents")}>
                前往学习资料 <span aria-hidden="true">→</span>
              </button>
            </div>
          </section>
        </div>
        )}
      </main>

      <dialog
        ref={profileDialog}
        className="profile-dialog"
        aria-labelledby="profile-dialog-title"
        onCancel={(event) => {
          event.preventDefault();
          setEditingProfile(false);
        }}
        onClose={() => setEditingProfile(false)}
      >
        <div className="profile-dialog-heading">
          <div>
            <p className="eyebrow">个人资料</p>
            <h2 id="profile-dialog-title">管理你的账号信息</h2>
          </div>
          <button
            className="dialog-close"
            type="button"
            aria-label="关闭个人资料"
            onClick={() => setEditingProfile(false)}
          >
            ×
          </button>
        </div>
        <form className="profile-form" onSubmit={handleProfileSubmit}>
          <label className="field-group">
            <span>姓名</span>
            <input
              type="text"
              name="display_name"
              autoComplete="name"
              autoFocus
              value={profileName}
              onChange={(event) => setProfileName(event.target.value)}
              maxLength={100}
              required
            />
          </label>
          <label className="field-group">
            <span>邮箱</span>
            <input type="email" value={user.email} readOnly />
          </label>
          <label className="field-group">
            <span>时区</span>
            <input
              type="text"
              name="timezone"
              value={profileTimezone}
              onChange={(event) => setProfileTimezone(event.target.value)}
              maxLength={100}
              aria-describedby="timezone-help"
              required
            />
          </label>
          <p className="field-help" id="timezone-help">
            使用 IANA 时区名称；新账号会自动采用当前设备时区。
          </p>
          {profileError && <p className="form-error" role="alert">{profileError}</p>}
          <div className="profile-actions">
            <button
              className="cancel-button"
              type="button"
              onClick={() => setEditingProfile(false)}
              disabled={savingProfile}
            >
              取消
            </button>
            <button className="primary-button" type="submit" disabled={savingProfile}>
              {savingProfile ? "正在保存…" : "保存修改"}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [connectionNotice, setConnectionNotice] = useState("");

  useEffect(() => {
    let isCurrent = true;
    requestAuth("/me")
      .then((profile) => {
        if (isCurrent) setUser(profile);
      })
      .catch((requestError) => {
        if (!isCurrent || requestError.status === 401) return;
        setConnectionNotice(requestError.message);
      })
      .finally(() => {
        if (isCurrent) setCheckingSession(false);
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  if (checkingSession) {
    return (
      <main className="session-check" aria-live="polite">
        <span className="loading-mark" aria-hidden="true">M</span>
        <p>正在打开你的学习空间…</p>
      </main>
    );
  }

  if (user) {
    return (
      <Dashboard
        user={user}
        onUserUpdated={setUser}
        onLoggedOut={() => setUser(null)}
      />
    );
  }

  return <AuthPage onAuthenticated={setUser} connectionNotice={connectionNotice} />;
}
