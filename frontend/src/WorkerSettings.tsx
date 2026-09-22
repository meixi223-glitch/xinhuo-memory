import { useEffect, useState, type FormEvent } from "react";
import {
  CaretDown,
  Check,
  Eye,
  EyeSlash,
  SlidersHorizontal,
} from "@phosphor-icons/react";
import { api } from "./api";
import type { WorkerConfig, WorkerProfile } from "./types";

function WorkerEditor({
  worker,
  onSaved,
  notify,
}: {
  worker: WorkerProfile;
  onSaved: (config: WorkerConfig) => void;
  notify: (text: string) => void;
}) {
  const [config, setConfig] = useState(worker.config);
  const [visible, setVisible] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState(false);
  const update = (field: keyof WorkerConfig, value: string) => {
    setConfig((c) => ({ ...c, [field]: value }));
    setDirty(true);
    setStatus("");
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (config.endpoint) {
      try {
        const url = new URL(config.endpoint);
        if (
          !["http:", "https:"].includes(url.protocol) ||
          url.username ||
          url.password
        )
          throw Error();
      } catch {
        setError(true);
        setStatus("请填写有效的 HTTP 或 HTTPS 地址，不包含账号密码。");
        return;
      }
    }
    if (!(config.model === "custom" ? config.custom : config.model).trim()) {
      setError(true);
      setStatus("请选择或填写工作模型。");
      return;
    }
    setBusy(true);
    try {
      await api.saveWorkerConfig(worker.id, config);
      onSaved(config);
      setDirty(false);
      setVisible(false);
      setError(false);
      setStatus("已保存到此浏览器，仅用于这项工作。");
      notify(`${worker.name}配置已保存在本机。`);
    } catch {
      setError(true);
      setStatus("本地存储不可用，配置仍保留在表单里。");
    } finally {
      setBusy(false);
    }
  };
  const clearKey = async () => {
    setBusy(true);
    try {
      await api.clearApiKey(worker.id);
      setConfig((c) => ({ ...c, apiKey: "" }));
      onSaved({ ...worker.config, apiKey: "" });
      setVisible(false);
      setError(false);
      setStatus("这项工作的本机密钥已清除。其他修改仍需保存。");
    } catch {
      setError(true);
      setStatus("清除失败，请检查浏览器存储权限。");
    } finally {
      setBusy(false);
    }
  };
  const selectedModel =
    worker.config.model === "custom"
      ? worker.config.custom
      : worker.models.find((m) => m.id === worker.config.model)?.name ||
        worker.config.model;
  return (
    <details
      className="worker-item"
      onToggle={(event) => {
        if (!event.currentTarget.open) setVisible(false);
      }}
    >
      <summary>
        <span className="worker-summary-copy">
          <strong>{worker.name}</strong>
          <span>{selectedModel || worker.description}</span>
        </span>
        <span className={`worker-badge ${selectedModel ? "configured" : ""}`}>
          {dirty ? "未保存" : selectedModel ? "已保存" : "待配置"}
        </span>
        <CaretDown size={17} className="worker-chevron" />
      </summary>
      <form
        onSubmit={save}
        aria-label={`${worker.name}配置`}
        className="worker-form"
      >
        <p className="worker-description">{worker.description}</p>
        <label>
          接口协议
          <select
            value={config.provider}
            onChange={(e) => update("provider", e.target.value)}
          >
            {!worker.providers.includes(config.provider) && (
              <option>{config.provider}</option>
            )}
            {worker.providers.map((provider) => (
              <option key={provider}>{provider}</option>
            ))}
          </select>
        </label>
        <label className="field-label">
          API 地址
          <input
            type="url"
            value={config.endpoint}
            onChange={(e) => update("endpoint", e.target.value)}
            placeholder="填写这项工作的服务地址"
            autoComplete="off"
          />
        </label>
        <label className="field-label" htmlFor={`key-${worker.id}`}>
          API Key
        </label>
        <div className="password-field">
          <input
            id={`key-${worker.id}`}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            type={visible ? "text" : "password"}
            value={config.apiKey}
            onChange={(e) => update("apiKey", e.target.value)}
            placeholder="只保存在这台设备"
          />
          <button
            type="button"
            className="icon-button"
            aria-label={visible ? "隐藏 API Key" : "显示 API Key"}
            onClick={() => setVisible((v) => !v)}
          >
            {visible ? <EyeSlash size={19} /> : <Eye size={19} />}
          </button>
        </div>
        <p className="field-help">
          此密钥仅用于{worker.name}的本地配置，不发送请求。
        </p>
        <label className="field-label">
          工作模型
          <select
            value={config.model}
            onChange={(e) => update("model", e.target.value)}
          >
            <option value="" disabled>
              选择一个工作模型
            </option>
            {config.model &&
              config.model !== "custom" &&
              !worker.models.some((m) => m.id === config.model) && (
                <option value={config.model}>{config.model}</option>
              )}
            {worker.models.map((m) => (
              <option value={m.id} key={m.id}>
                {m.name}
              </option>
            ))}
            <option value="custom">手动填写模型 ID</option>
          </select>
        </label>
        {config.model === "custom" && (
          <label className="field-label">
            模型 ID
            <input
              required
              value={config.custom}
              onChange={(e) => update("custom", e.target.value)}
              placeholder="填写服务商提供的模型 ID"
            />
          </label>
        )}
        {status && (
          <p
            className={`form-status ${error ? "error" : "success"}`}
            role="status"
          >
            {status}
          </p>
        )}
        <button
          type="submit"
          className="button primary full save-model"
          disabled={busy}
        >
          {busy ? "保存中…" : `保存${worker.name}配置`}
        </button>
        {config.apiKey && (
          <button
            type="button"
            className="text-button clear-key"
            onClick={clearKey}
            disabled={busy}
          >
            清除本机密钥
          </button>
        )}
      </form>
    </details>
  );
}

export function WorkerSettings({ notify }: { notify: (text: string) => void }) {
  const [workers, setWorkers] = useState<WorkerProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setFailed(false);
    api
      .getWorkerProfiles()
      .then((profiles) => {
        if (active) setWorkers(profiles);
      })
      .catch(() => {
        if (active) setFailed(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  const configured = workers.filter((w) =>
    (w.config.model === "custom" ? w.config.custom : w.config.model).trim(),
  ).length;
  return (
    <section
      className="card settings-card worker-settings"
      aria-labelledby="worker-heading"
    >
      <div className="section-head">
        <h2 id="worker-heading">工作模型</h2>
        <SlidersHorizontal size={21} />
      </div>
      <p className="worker-intro">不同工作，各自选择合适的模型。</p>
      {loading ? (
        <div
          className="worker-loading"
          role="status"
          aria-label="正在加载工作模型"
        >
          <div className="skeleton sk-line" />
          <div className="skeleton sk-line" />
          <span className="sr-only">正在读取工作模型配置</span>
        </div>
      ) : failed ? (
        <div className="worker-empty">
          <p>工作模型配置暂时没有读到。</p>
          <button
            className="button soft"
            onClick={() => setAttempt((n) => n + 1)}
          >
            重新读取配置
          </button>
        </div>
      ) : workers.length ? (
        <>
          <div className="worker-count">
            <Check size={15} />
            <span>
              {configured} / {workers.length} 项已保存到本机
            </span>
          </div>
          <div className="worker-list">
            {workers.map((worker) => (
              <WorkerEditor
                key={worker.id}
                worker={worker}
                notify={notify}
                onSaved={(config) =>
                  setWorkers((all) =>
                    all.map((w) => (w.id === worker.id ? { ...w, config } : w)),
                  )
                }
              />
            ))}
          </div>
        </>
      ) : (
        <div className="worker-empty">
          <p>还没有可配置的工作模型。</p>
          <span>工作清单到来后，各项配置会出现在这里。</span>
        </div>
      )}
      <p className="field-help worker-footnote">
        工作清单与候选模型来自配置。当前为演示选项，也可以手动填写模型
        ID；保存不会连接服务或启动工作。
      </p>
    </section>
  );
}
