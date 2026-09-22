import { useEffect, useState } from "react";
import { api } from "./api";
type Rule = {
  id: string;
  name: string;
  components: string[];
  min_component: number;
  min_total: number;
  priority: number;
  enabled: boolean;
};
export function EmotionRules() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  useEffect(() => {
    api
      .rules()
      .then((r) => setRules(r.items))
      .catch(() => setError("命名规则未能读取，请刷新重试。"));
  }, []);
  return (
    <section className="card settings-card">
      <details>
        <summary>情绪名称与配方规则</summary>
        <p className="field-help">
          名称根据八种基础情绪变化量实时计算；修改名称不会重写原始自述。
        </p>
        {rules.map((rule) => (
          <form
            className="rule-form"
            key={rule.id}
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(rule.id);
              setError("");
              try {
                const r = await api.tool<{ items: Rule[] }>(
                  "mood_composite_rule_set",
                  rule,
                );
                setRules(r.items);
                setError("规则已保存；刷新状态页即可查看新名称。");
              } catch (e) {
                setError(e instanceof Error ? e.message : "保存失败");
              } finally {
                setBusy("");
              }
            }}
          >
            <label className="field-label">
              {rule.components.join(" + ")}
              <input
                aria-label={`${rule.id} 情绪名称`}
                maxLength={16}
                required
                value={rule.name}
                onChange={(e) =>
                  setRules((all) =>
                    all.map((r) =>
                      r.id === rule.id ? { ...r, name: e.target.value } : r,
                    ),
                  )
                }
              />
            </label>
            <div className="action-row">
              <label>
                每种最低变化
                <input
                  type="number"
                  min={0}
                  max={0.18}
                  step={0.01}
                  value={rule.min_component}
                  onChange={(e) =>
                    setRules((all) =>
                      all.map((r) =>
                        r.id === rule.id
                          ? { ...r, min_component: Number(e.target.value) }
                          : r,
                      ),
                    )
                  }
                />
              </label>
              <label>
                合计最低变化
                <input
                  type="number"
                  min={0}
                  max={0.72}
                  step={0.01}
                  value={rule.min_total}
                  onChange={(e) =>
                    setRules((all) =>
                      all.map((r) =>
                        r.id === rule.id
                          ? { ...r, min_total: Number(e.target.value) }
                          : r,
                      ),
                    )
                  }
                />
              </label>
            </div>
            <button className="button soft" disabled={!!busy}>
              {busy === rule.id ? "保存中…" : `保存 ${rule.id}`}
            </button>
          </form>
        ))}
        {error && <p role="status">{error}</p>}
      </details>
    </section>
  );
}
