// Mock configuration. Replace through api.getConfig() when the backend is ready.
export type EmotionConfig = {
  dimensions: { id: string; name: string; color: string }[];
  quadrants: string[];
  compositeRules: { label: string; when: Record<string, number> }[];
  vaRules: { label: string; v: [number, number]; a: [number, number] }[];
  fallbackLabel: string;
};
export const mockEmotionConfig: EmotionConfig = {
  quadrants: ["兴奋", "紧张", "低落", "平静"],
  dimensions: [
    { id: "joy", name: "喜悦", color: "#bd7054" },
    { id: "anticipation", name: "期待", color: "#ad8735" },
    { id: "trust", name: "信任", color: "#6c8e71" },
    { id: "surprise", name: "惊讶", color: "#538a89" },
    { id: "sadness", name: "悲伤", color: "#6b83a0" },
    { id: "fear", name: "恐惧", color: "#9380a6" },
    { id: "disgust", name: "厌恶", color: "#87916b" },
    { id: "anger", name: "愤怒", color: "#ad6575" },
  ],
  compositeRules: [
    { label: "惊喜", when: { joy: 0.55, surprise: 0.35 } },
    { label: "期待", when: { anticipation: 0.5 } },
    { label: "安心", when: { trust: 0.5 } },
  ],
  vaRules: [
    { label: "惊喜", v: [0.25, 1], a: [0.25, 1] },
    { label: "放松", v: [0.25, 1], a: [-1, -0.25] },
    { label: "愉悦", v: [0.25, 1], a: [-0.25, 0.25] },
    { label: "紧张", v: [-1, -0.25], a: [0.25, 1] },
    { label: "低落", v: [-1, -0.25], a: [-1, -0.25] },
    { label: "难过", v: [-1, -0.25], a: [-0.25, 0.25] },
    { label: "振奋", v: [-0.25, 0.25], a: [0.25, 1] },
    { label: "平静", v: [-0.25, 0.25], a: [-1, -0.25] },
  ],
  fallbackLabel: "平和",
};

export function resolveComposite(
  dimensions: Record<string, number | null>,
  config: EmotionConfig,
): string {
  return (
    config.compositeRules.find((rule) =>
      Object.entries(rule.when).every(
        ([key, minimum]) => (dimensions[key] ?? -1) >= (minimum ?? 0),
      ),
    )?.label || config.fallbackLabel
  );
}
export function resolveVa(v: number, a: number, config: EmotionConfig) {
  return (
    config.vaRules.find(
      (r) => v >= r.v[0] && v <= r.v[1] && a >= r.a[0] && a <= r.a[1],
    )?.label || config.fallbackLabel
  );
}
