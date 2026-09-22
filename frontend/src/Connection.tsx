import { useState, type FormEvent } from "react";
import { Flame, LockKey, ArrowRight } from "@phosphor-icons/react";
import { api } from "./api";
export function Connection({ connected }: { connected: () => void }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function login(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(token);
      setToken("");
      connected();
    } catch {
      setError("连接未成功，请检查 Token 或服务状态；连续失败后需稍候再试。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="connection-layout">
      <div className="connection-copy">
        <Flame size={42} weight="fill" />
        <p className="overline">XINHUO · MEMORY ROOM</p>
        <h1>
          让记忆，
          <br />
          有处安放。
        </h1>
        <p>
          保存走过的片刻，照看当下的感受。
          <br />
          从连接你自己的记忆库开始。
        </p>
        <div className="connection-points">
          <span>本地存储</span>
          <span>证据可追溯</span>
          <span>独立工作模型</span>
        </div>
      </div>
      <form className="card settings-card connection-form" onSubmit={login}>
        <LockKey size={25} />
        <h2>连接记忆库</h2>
        <p className="muted">
          输入部署时设置的访问 Token。登录后，在设置中填写工作模型 API。
        </p>
        <label className="field-label">
          访问 Token
          <input
            type="password"
            autoComplete="current-password"
            required
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="输入 MEMORY_TOKEN"
          />
        </label>
        {error && (
          <p className="form-status error" role="alert">
            {error}
          </p>
        )}
        <button className="button primary full" disabled={busy}>
          {busy ? "正在连接…" : "进入记忆观察室"}
          <ArrowRight size={18} />
        </button>
        <p className="field-help">
          Token 不存入浏览器本地存储。会话有效期为 12 小时，可随时退出。
        </p>
      </form>
    </section>
  );
}
