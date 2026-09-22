import { useState, type FormEvent } from "react";
import { api } from "./api";
import type { Entry } from "./types";
export function LibraryTools({
  refresh,
  detail,
}: {
  refresh: () => void;
  detail: (entry: Entry) => void;
}) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [hits, setHits] = useState<Entry[] | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [searched, setSearched] = useState("");
  const [recall, setRecall] = useState<
    { id: string; title: string; body: string }[] | null
  >(null);
  const [candidates, setCandidates] = useState<
    { id: string; content: string; summary: string; fact_key: string }[] | null
  >(null);
  async function run(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      await fn();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "操作未完成。");
    } finally {
      setBusy(false);
    }
  }
  const ingest = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api.ingest(text, requestId);
      setText("");
      setRequestId(crypto.randomUUID());
      setMessage("已保存原始片段，工作模型配置完成后自动整理。");
      refresh();
    });
  };
  async function search(offset = 0) {
    const q = offset ? searched : query;
    const result = await api.getEntries(offset, q);
    setHits((old) =>
      offset ? [...(old || []), ...result.items] : result.items,
    );
    setSearched(q);
    setNext(result.nextOffset);
  }
  return (
    <section className="card settings-card library-tools">
      <details>
        <summary>添加片段与查找记忆</summary>
        <div className="worker-form">
          <form onSubmit={ingest}>
            <label className="field-label">
              留下一段片段
              <textarea
                required
                maxLength={12000}
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  setRequestId(crypto.randomUUID());
                }}
                placeholder="输入需要保留的事件；由工人整理并核对证据。"
              />
            </label>
            <button className="button primary" disabled={busy || !text.trim()}>
              保存片段
            </button>
          </form>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(() => search());
            }}
          >
            <label className="field-label">
              全库查找
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="在全部记忆与事件中查找"
              />
            </label>
            <div className="action-row">
              <button className="button soft" disabled={busy || !query.trim()}>
                全文查找
              </button>
              <button
                className="button soft"
                type="button"
                disabled={busy || !query.trim()}
                onClick={() =>
                  run(async () => {
                    const r = await api.tool<{
                      memories?: {
                        id: string;
                        summary?: string;
                        content?: string;
                        text?: string;
                      }[];
                      items?: {
                        id: string;
                        summary?: string;
                        content?: string;
                        text?: string;
                      }[];
                      degraded?: string[];
                    }>("memory_recall", { query });
                    setRecall(
                      (r.memories || r.items || []).map((m) => ({
                        id: m.id,
                        title: m.summary || m.id,
                        body: m.content || m.text || "",
                      })),
                    );
                    setMessage(
                      r.degraded?.length
                        ? "召回已降级，请检查工作模型配置。"
                        : "召回完成，结果与实际返回一致。",
                    );
                  })
                }
              >
                测试召回
              </button>
            </div>
          </form>
          {hits !== null && (
            <div>
              <h3>全库查找 · {hits.length} 条已加载</h3>
              {hits.map((e) => (
                <button
                  className="search-hit"
                  key={e.kind + e.id}
                  onClick={() => detail(e)}
                >
                  {e.title}
                </button>
              ))}
              {!hits.length && <p>没有匹配条目。</p>}
              {next !== null && (
                <button
                  className="button soft"
                  disabled={busy}
                  onClick={() => run(() => search(next))}
                >
                  继续加载搜索结果
                </button>
              )}
            </div>
          )}
          {recall !== null && (
            <div>
              <h3>本次召回</h3>
              {recall.map((r) => (
                <p key={r.id}>
                  {r.title}
                  <br />
                  {r.body}
                </p>
              ))}
              {!recall.length && <p>本次没有返回记忆。</p>}
            </div>
          )}
          <button
            className="button soft"
            disabled={busy}
            onClick={() =>
              run(async () => setCandidates((await api.candidates()).items))
            }
          >
            查看待审核候选（最多 100 条）
          </button>
          {candidates?.map((c) => (
            <article className="review-item" key={c.id}>
              <p>{c.summary || c.content}</p>
              <small>
                {c.id} · {c.fact_key}
              </small>
              <div className="action-row">
                <button
                  className="button soft"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api.tool("memory_review", {
                        id: c.id,
                        action: "approve",
                      });
                      setCandidates((v) => v!.filter((x) => x.id !== c.id));
                      setMessage("已通过审核。");
                      refresh();
                    })
                  }
                >
                  通过审核
                </button>
                <button
                  className="button soft"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api.tool("memory_review", {
                        id: c.id,
                        action: "reject",
                      });
                      setCandidates((v) => v!.filter((x) => x.id !== c.id));
                      setMessage("已归档候选。");
                      refresh();
                    })
                  }
                >
                  拒绝并归档
                </button>
              </div>
            </article>
          ))}
          {candidates?.length === 0 && <p>没有待审核候选。</p>}
          <p className="field-help">
            冲突候选需通过 MCP memory_review 的 replace
            操作明确指定被替代条目。不会自动覆盖旧事实。
          </p>
          {message && <p role="status">{message}</p>}
        </div>
      </details>
    </section>
  );
}
export function MemoryActions({
  entry,
  done,
}: {
  entry: Entry;
  done: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function act(name: string, args: Record<string, unknown>) {
    setBusy(true);
    try {
      await api.tool(name, { id: entry.id, ...args });
      done();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }
  if (entry.kind !== "memory") return null;
  return (
    <div>
      <div className="action-row">
        <button
          className="button soft"
          disabled={busy}
          onClick={() => act("memory_pin", { pinned: !entry.pinned })}
        >
          {entry.pinned ? "取消固定" : "固定记忆"}
        </button>
        <button
          className="button soft"
          disabled={busy}
          onClick={() =>
            act(
              entry.versionStatus === "archived"
                ? "memory_restore"
                : "memory_archive",
              { reason: "owner_room_action" },
            )
          }
        >
          {entry.versionStatus === "archived" ? "恢复记忆" : "归档记忆"}
        </button>
      </div>
      <p className="field-help">
        归档保留历史记录；可通过 MCP memory_restore 恢复。
      </p>
      {message && <p role="alert">{message}</p>}
    </div>
  );
}
