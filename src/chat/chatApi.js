import { apiUrl } from "../api.js";

const API = "/api/chat";

// Shared by the app shell (session list) and the chat page (messages), so both
// surfaces agree on how chat failures are shown.
export async function chatRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(`${API}${path}`), {
      method: options.method || "GET",
      credentials: "include",
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: AbortSignal.timeout(60000),
    });
  } catch {
    throw new Error("无法连接问答服务，请检查网络后重试。");
  }

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

export function formatSessionTitle(session, t) {
  return session.title || t("新对话");
}
