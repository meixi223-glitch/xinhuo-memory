import type { WorkerDefinition } from "../types";

// Demo catalogue only. The adapter can replace roles, protocols and model choices
// together when the backend supplies its actual worker inventory.
const generation = {
  kind: "generation" as const,
  providers: ["OpenAI 兼容", "Anthropic", "Gemini", "Ollama", "其他"],
  models: [
    { id: "mock-worker-balanced", name: "均衡模型（演示）" },
    { id: "mock-worker-light", name: "轻量模型（演示）" },
  ],
};
export const mockWorkers: WorkerDefinition[] = [
  {
    ...generation,
    id: "memory-curation",
    name: "记忆整理",
    description: "从事件里提取、合并和整理记忆。",
  },
  {
    ...generation,
    id: "memory-review",
    name: "记忆复核",
    description: "检查记忆的证据、质量与保留价值。",
  },
  {
    ...generation,
    id: "recall-selector",
    name: "召回筛选",
    description: "为当前对话挑选相关记忆。",
  },
  {
    ...generation,
    id: "emotion",
    name: "情绪自评",
    description: "由 AI 选择情绪并写下理由与原话。",
  },
  {
    ...generation,
    id: "scene",
    name: "情景帧",
    description: "更新焦点、阶段、当下感受与转场。",
  },
  {
    ...generation,
    id: "impression",
    name: "每日印象",
    description: "整理一天的事件与整体印象。",
  },
  {
    id: "embedding",
    name: "向量嵌入",
    description: "把记忆转成用于检索的向量。",
    kind: "embedding",
    providers: ["OpenAI 兼容", "Ollama", "其他"],
    models: [{ id: "mock-embedding", name: "嵌入模型（演示）" }],
  },
  {
    id: "reranker",
    name: "检索重排序",
    description: "对检索候选重新排序，提高相关性。",
    kind: "reranking",
    providers: ["Cohere 兼容", "其他"],
    models: [{ id: "mock-reranker", name: "重排序模型（演示）" }],
  },
];
