/**
 * Sole data boundary for the UI. MOCK ONLY: no fetch, XHR, WebSocket, model calls,
 * analytics, or remote API endpoints. Replace the mock implementations here when
 * the backend contract is agreed. Components consume typed domain objects only.
 * API keys stay in this browser's localStorage and never enter a request.
 */
import type { Snapshot, WorkerConfig, WorkerProfile } from "./types";
import { mockWorkers } from "./mocks/workers";
import { demo } from "./mocks/snapshot";
import {
  mockEmotionConfig,
  resolveComposite,
  type EmotionConfig,
} from "./config";
const defaults: WorkerConfig = {
  endpoint: "",
  model: "",
  custom: "",
  provider: "OpenAI 兼容",
  apiKey: "",
};
function read<T>(key: string, fallback: T): T {
  try {
    const str = localStorage.getItem(key);
    return str ? JSON.parse(str) : fallback;
  } catch {
    return fallback;
  }
}
function write(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value));
}
const delay = (ms = 350) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));
function normalizeConfig(
  value: unknown,
  provider = defaults.provider,
): WorkerConfig {
  const saved =
    value && typeof value === "object" ? (value as Partial<WorkerConfig>) : {};
  return Object.fromEntries(
    Object.entries({ ...defaults, provider }).map(([k, v]) => [
      k,
      typeof saved[k as keyof WorkerConfig] === "string"
        ? saved[k as keyof WorkerConfig]
        : v,
    ]),
  ) as WorkerConfig;
}
function readWorkerConfigs(): Record<string, WorkerConfig> {
  const saved = read<{
    version?: number;
    configurations?: Record<string, WorkerConfig>;
  } | null>("xinhuo-worker-configs", null);
  if (
    saved?.version === 2 &&
    saved.configurations &&
    typeof saved.configurations === "object" &&
    !Array.isArray(saved.configurations)
  ) {
    return saved.configurations;
  }
  const legacy = read<WorkerConfig | null>("xinhuo-model-config", null);
  // A legacy shared config belongs only to memory curation; never copy its key to other roles.
  return legacy ? { "memory-curation": normalizeConfig(legacy) } : {};
}
export const api = {
  async getConfig(): Promise<EmotionConfig> {
    await delay(80);
    return structuredClone(mockEmotionConfig);
  },
  async getSnapshot(): Promise<Snapshot> {
    await delay(550);
    const result = structuredClone(demo);
    result.mood.label = resolveComposite(
      result.mood.dimensions,
      mockEmotionConfig,
    );
    return result;
  },
  async getDailyNotes(): Promise<Record<string, string>> {
    const value = read<Record<string, string>>("xinhuo-daily-notes", {});
    return Object.fromEntries(
      Object.entries(value || {}).filter(([, v]) => typeof v === "string"),
    );
  },
  async saveDailyNote(
    day: string,
    text: string,
  ): Promise<Record<string, string>> {
    const notes = { ...(await api.getDailyNotes()), [day]: text };
    write("xinhuo-daily-notes", notes);
    return notes;
  },
  async getWorkerProfiles(): Promise<WorkerProfile[]> {
    await delay(250);
    const configs = readWorkerConfigs();
    return structuredClone(mockWorkers).map((worker) => ({
      ...worker,
      config: normalizeConfig(configs[worker.id], worker.providers[0]),
    }));
  },
  async saveWorkerConfig(
    workerId: string,
    config: WorkerConfig,
  ): Promise<void> {
    // Read/merge/write synchronously, so independent saves cannot erase siblings.
    const configurations = {
      ...readWorkerConfigs(),
      [workerId]: normalizeConfig(config),
    };
    write("xinhuo-worker-configs", { version: 2, configurations });
    // Only retire the old slot after a successful write; its key migrates once.
    localStorage.removeItem("xinhuo-model-config");
  },
  async clearApiKey(workerId: string): Promise<void> {
    const config = normalizeConfig(readWorkerConfigs()[workerId]);
    await api.saveWorkerConfig(workerId, { ...config, apiKey: "" });
  },
  getTheme(): string {
    return read("xinhuo-theme", "system");
  },
  saveTheme(theme: string): void {
    write("xinhuo-theme", theme);
  },
};
