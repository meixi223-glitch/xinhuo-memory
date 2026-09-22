import type { Entry } from "./types";

export function mergeEntries(entries: Entry[]) {
  const map = new Map<string, Entry>();
  for (const e of entries) {
    const key = e.canonicalId || e.id;
    const prev = map.get(key);
    map.set(
      key,
      prev
        ? {
            ...(e.kind === "memory" ? e : prev),
            channels: [...new Set([...prev.channels, ...e.channels])],
            tags: [...new Set([...prev.tags, ...e.tags])],
            at: prev.at > e.at ? prev.at : e.at,
          }
        : e,
    );
  }
  return [...map.values()].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}
export const time = (s: string) =>
  new Date(s).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
export const date = (s: string) =>
  new Date(s).toLocaleDateString("zh-CN", { month: "long", day: "numeric" });
export const signed = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
