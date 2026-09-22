/** Sole browser data boundary. Tokens stay in an HttpOnly server session. */
import type { Snapshot, WorkerConfig, WorkerProfile, Entry } from "./types";
import type { EmotionConfig } from "./config";
export class AuthError extends Error {}
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(60000),
  });
  if (response.status === 401) {
    window.dispatchEvent(new Event("xinhuo-auth-required"));
    throw new AuthError("请登录记忆库。");
  }
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(value.error || "请求未完成，请稍后重试。");
  return value as T;
}
export const api = {
  session: () => request<{ authenticated: boolean }>("/api/session"),
  login: (token: string) => request("/api/login", { token }),
  logout: () => request("/api/logout", {}),
  getConfig: () => request<EmotionConfig>("/api/emotions"),
  getSnapshot: () => request<Snapshot>("/api/snapshot"),
  getEntries: (offset = 0, query = "") =>
    request<{ items: Entry[]; nextOffset: number | null }>(
      `/api/entries?offset=${offset}&query=${encodeURIComponent(query)}`,
    ),
  getDailyNotes: () => request<Record<string, string>>("/api/notes"),
  saveDailyNote: (day: string, text: string) =>
    request<Record<string, string>>("/api/notes", { day, text }),
  getWorkerProfiles: () => request<WorkerProfile[]>("/api/workers"),
  saveWorkerConfig: (workerId: string, config: WorkerConfig) =>
    request<void>(`/api/workers/${encodeURIComponent(workerId)}`, config),
  clearApiKey: (workerId: string) =>
    request<void>(`/api/workers/${encodeURIComponent(workerId)}`, {
      clearApiKey: true,
    }),
  testWorker: (workerId: string) =>
    request(`/api/workers/${encodeURIComponent(workerId)}/test`, {}),
  ingest: (content: string, sourceMsgId: string) =>
    request("/api/events", {
      content,
      source: "room",
      channel: "chat",
      role: "user",
      session_id: "room",
      source_msg_id: sourceMsgId,
    }),
  tool: <T = Record<string, unknown>>(
    name: string,
    args: Record<string, unknown>,
  ) => request<T>("/api/tool", { name, arguments: args }),
  candidates: () =>
    request<{
      items: {
        id: string;
        content: string;
        summary: string;
        fact_key: string;
      }[];
    }>("/api/candidates"),
  rules: () =>
    request<{
      items: {
        id: string;
        name: string;
        components: string[];
        min_component: number;
        min_total: number;
        priority: number;
        enabled: boolean;
      }[];
    }>("/api/composite-rules"),
  getTheme(): string {
    try {
      return localStorage.getItem("xinhuo-theme") || "system";
    } catch {
      return "system";
    }
  },
  saveTheme(theme: string) {
    localStorage.setItem("xinhuo-theme", theme);
  },
};
