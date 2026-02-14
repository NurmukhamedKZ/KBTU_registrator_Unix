const RAW_API_BASE_URL = (import.meta.env.VITE_API_URL || "").trim();
const API_BASE_URL = RAW_API_BASE_URL.replace(/\/+$/, "");

function withApiBase(path) {
  if (!API_BASE_URL) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiRequest(path, options = {}) {
  const url = withApiBase(path);
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const expectsJson = options.expectsJson !== false;
  const data = contentType.includes("application/json") ? await response.json() : null;

  if (expectsJson && !contentType.includes("application/json")) {
    throw new Error(
      `API ${url} returned non-JSON response (${response.status}). Check backend/proxy configuration.`
    );
  }

  if (!response.ok) {
    const message = data?.detail || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return data;
}

export function startSingleAgent(payload) {
  return apiRequest("/api/agent/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function startBatchAgent(payload) {
  return apiRequest("/api/agent/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function stopAgent(sessionId) {
  return apiRequest("/api/agent/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function getAgentStatus(sessionId) {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return apiRequest(`/api/agent/status${qs}`);
}

export function getAgentLogs(sessionId) {
  if (!sessionId) return Promise.resolve([]);
  return apiRequest(`/api/agent/logs?session_id=${encodeURIComponent(sessionId)}`);
}

export function getQuestions(limit, offset) {
  return apiRequest(`/api/questions?limit=${limit}&offset=${offset}`);
}
