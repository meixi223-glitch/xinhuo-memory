export type Channel = "企微" | "聊天" | "论坛" | "其他";
export type Entry = {
  pinned?: boolean;
  versionStatus?: string;
  layer?: string;
  id: string;
  title: string;
  body: string;
  at: string;
  channels: Channel[];
  kind: "event" | "memory";
  canonicalId?: string;
  tags: string[];
  emotion?: string;
  quote?: string;
};
export type Report = {
  id: string;
  at: string;
  v: number;
  a: number;
  label: string;
  reason: string;
  quote: string;
};
export type Impression = {
  day: string;
  summary: string;
  theme: string;
  source: string;
};
export type Snapshot = {
  nextOffset?: number | null;
  wakePolicy?: {
    skip_proactive: boolean;
    interval_factor: number;
    proactive_policy: string;
  };
  relationships?: {
    names: Record<string, string>;
    vector: Record<string, number>;
  };
  source: "demo" | "live";
  capturedAt: string;
  expiresAt: string | null;
  mood: {
    v: number | null;
    a: number | null;
    label: string;
    updatedAt: string;
    dimensionMode?: "delta";
    dimensions: Record<string, number | null>;
    note: string;
  };
  scene: {
    focus: string;
    phase: string;
    body: string;
    transition: string;
    expiresAt: string | null;
    raw?: string;
  };
  entries: Entry[];
  reports: Report[];
  impressions: Impression[];
  recalls: {
    id: string;
    at: string;
    channel: Channel;
    query: string;
    items: { id: string; title: string; reason: string }[];
  }[];
  unknown: { id: string; text: string; at: string }[];
  stats: {
    memories: number;
    events: number;
    recalls: number;
    impressions: number;
    today: number;
    pending: number;
    done: number;
    failed: number;
    projected: number;
    projectionTotal: number;
  };
};

export type WorkerConfig = {
  hasApiKey?: boolean;
  endpoint: string;
  model: string;
  custom: string;
  provider: string;
  apiKey: string;
};
export type ModelOption = { id: string; name: string };
export type WorkerDefinition = {
  id: string;
  name: string;
  description: string;
  kind: "generation" | "embedding" | "reranking";
  providers: string[];
  models: ModelOption[];
};
export type WorkerProfile = WorkerDefinition & { config: WorkerConfig };
