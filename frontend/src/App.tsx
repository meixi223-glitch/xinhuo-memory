import { useEffect, useRef, useState, useMemo, type ReactNode } from "react";
import {
  Flame,
  Heartbeat,
  Brain,
  Notebook,
  SlidersHorizontal,
  ArrowUpRight,
  ArrowRight,
  X,
  Plus,
  MagnifyingGlass,
  Sun,
  Moon,
  Clock,
  Sparkle,
  BookmarkSimple,
  ChatCircle,
  CalendarBlank,
  Info,
  Plant,
  Quotes,
  ArrowClockwise,
  Database,
  Check,
  CaretRight,
  PlugsConnected,
  WarningCircle,
  DoorOpen,
  ShieldCheck,
  DownloadSimple,
} from "@phosphor-icons/react";
import type { Snapshot, Entry, Report, Channel } from "./types";
import { mergeEntries, time, date, signed } from "./data";
import { api } from "./api";
import { WorkerSettings } from "./WorkerSettings";
import type { EmotionConfig } from "./config";

type Page = "status" | "memory" | "records" | "settings";
const pages = [
  ["status", "状态", Heartbeat],
  ["memory", "记忆", Brain],
  ["records", "记录", Notebook],
  ["settings", "设置", SlidersHorizontal],
] as const;
const getPage = (): Page => {
  const h = location.hash.slice(1).split("/")[0];
  return pages.some((p) => p[0] === h) ? (h as Page) : "status";
};
function Empty({ text, detail }: { text: string; detail?: string }) {
  return (
    <div className="empty">
      <Plant size={30} />
      <h3>{text}</h3>
      <p>{detail || "换一个筛选条件，再找找看。"}</p>
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? "wide" : ""}`}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      aria-labelledby="modal-title"
    >
      <div className="modal-head">
        <h2 id="modal-title">{title}</h2>
        <button className="icon-button" aria-label="关闭弹窗" onClick={onClose}>
          <X size={21} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function Chip({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={`chip ${className}`}>{children}</span>;
}
function Source({ channel }: { channel: string }) {
  return (
    <span className={`source source-${channel}`}>
      <ChatCircle size={12} />
      {channel}
    </span>
  );
}
function SectionHead({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children?: ReactNode;
}) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {sub && <p>{sub}</p>}
      </div>
      {children}
    </div>
  );
}
function MoodWheel({
  mood,
  config,
}: {
  mood: Snapshot["mood"];
  config: EmotionConfig;
}) {
  const ready = mood.v !== null && mood.a !== null;
  const angle = ready ? Math.atan2(mood.a!, mood.v!) : 0;
  const px = 50 + Math.cos(angle) * 47.6;
  const py = 50 - Math.sin(angle) * 47.6;
  return (
    <div className="wheel-wrap">
      <span className="axis-label axis-top">
        高唤醒 <span>AROUSAL</span>
      </span>
      <span className="axis-label axis-left">不愉悦</span>
      <span className="axis-label axis-right">愉悦</span>
      <span className="axis-label axis-bottom">低唤醒</span>
      <div className="wheel">
        <div className="ring-color" />
        <div className="wheel-interior" />
        <div className="axis horizontal" />
        <div className="axis vertical" />
        <div className="wheel-dashes" />
        {config.quadrants.map((q, i) => (
          <span
            className={`quad q-${["one", "two", "three", "four"][i]}`}
            key={i}
          >
            {q}
          </span>
        ))}
        <div className="wheel-center">
          <span>此刻的情绪</span>
          <strong>{mood.label}</strong>
          <small>{ready ? "正在被好好感受" : "等待情绪状态"}</small>
        </div>
        {ready && (
          <div
            className="emotion-position"
            style={{ left: `${px}%`, top: `${py}%` }}
          >
            <span className="emotion-dot" />
            <span className="emotion-tag">
              {mood.label}
              <Sparkle size={12} weight="fill" />
            </span>
          </div>
        )}
      </div>
      <div className="va-readout">
        <span>
          效价 <b>v {ready ? signed(mood.v!) : "未提供"}</b>
        </span>
        <span>
          唤醒 <b>a {ready ? signed(mood.a!) : "未提供"}</b>
        </span>
      </div>
    </div>
  );
}
function Scene({
  scene,
  onInfo,
}: {
  scene: Snapshot["scene"];
  onInfo: () => void;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const remaining = scene.expiresAt
    ? Math.max(0, Date.parse(scene.expiresAt) - now)
    : 0;
  const stale = !scene.expiresAt || remaining === 0;
  const seconds = Math.ceil(remaining / 1000);
  return (
    <section className={`scene-card ${stale ? "stale" : ""}`}>
      <div className="section-head">
        <h2>眼里的现在</h2>
        <button
          className="icon-button"
          aria-label="查看情景帧说明"
          onClick={onInfo}
        >
          <Info size={19} />
        </button>
      </div>
      {!scene.expiresAt && !scene.focus ? (
        <Empty
          text="现在，还没有被描画"
          detail="新的情景帧到来后，焦点、阶段和此刻的感受会出现在这里。"
        />
      ) : (
        <>
          <div className="freshness">
            <span className="fresh-dot" />
            {stale ? "stale · 等待新的情景帧" : "情景帧保鲜中"}
            <span>
              <Clock size={13} />
              {stale
                ? "已过期"
                : `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`}
            </span>
          </div>
          <dl className="scene-fields">
            {[
              ["焦点", scene.focus],
              ["阶段", scene.phase],
              ["状态", scene.body],
            ].map(([a, b]) => (
              <div key={a}>
                <dt>{a}</dt>
                <dd>{b || "尚未记录"}</dd>
              </div>
            ))}
          </dl>
          <div className="scene-transition">
            <Quotes size={20} weight="fill" />
            <p>{scene.transition || "下一次对话，会带来新的现在。"}</p>
          </div>
        </>
      )}
      <div className="scene-foot">
        <span>时间会走，理解也需要更新</span>
        <span className="leaf-mark">
          <Plant size={22} />
        </span>
      </div>
    </section>
  );
}
function Status({
  data,
  config,
  reports,
  go,
  detail,
  info,
}: {
  data: Snapshot;
  config: EmotionConfig;
  reports: Report[];
  go: (p: Page, section?: string) => void;
  detail: (e: Entry) => void;
  info: (title: string, body: string) => void;
}) {
  const entries = mergeEntries(data.entries).filter((e) => e.kind === "memory");
  return (
    <>
      <div className="page-intro">
        <div>
          <p className="overline">
            {new Date().toLocaleDateString("zh-CN", {
              year: "numeric",
              month: "long",
              day: "numeric",
              weekday: "long",
            })}
          </p>
          <h1>
            {data.mood.v === null
              ? "等一份此刻的感受。"
              : `此刻，有一点${data.mood.label}。`}
          </h1>
          <p>状态有迹可循，记忆慢慢生长。</p>
        </div>
      </div>
      <div className="status-grid">
        <section className="mood-card card">
          <SectionHead title="情绪的形状">
            <button
              className="text-button quiet"
              onClick={() =>
                info(
                  "关于这枚情绪圆环",
                  `横轴是效价 v（不愉悦到愉悦），纵轴是唤醒 a（低到高），均为 -1 到 +1。圆环上的点用方向表示状态，精确强度以 v/a 数字为准。点的呼吸动效不改变真实数值。\n\n${data.mood.note}\n\n这是 AI 当前的情绪状态；AI 自己选择、填写的自评单独保存在记录页。基础情绪与复合命名从配置读取，可以替换。`,
                )
              }
            >
              Russell 双轴圆环 <Info size={14} />
            </button>
          </SectionHead>
          {data.mood.v === null ? (
            <Empty
              text="还没有情绪坐标"
              detail="第一份情绪状态到来后，圆环上的光点会在这里亮起。"
            />
          ) : (
            <div className="mood-layout">
              <MoodWheel mood={data.mood} config={config} />
              <div className="emotion-components">
                <div className="components-title">
                  <span>此刻的情绪配方</span>
                  <span>分量</span>
                </div>
                {config.dimensions.map(({ id, name, color }) => {
                  const val = data.mood.dimensions[id];
                  return (
                    <div className="component-row" key={id}>
                      <span>{name}</span>
                      <div className="component-track">
                        <div
                          style={{
                            width: `${(val ?? 0) * 100}%`,
                            background: color,
                          }}
                        />
                      </div>
                      <b>
                        {val == null ? "未提供" : `${Math.round(val * 100)}%`}
                      </b>
                    </div>
                  );
                })}
                <div className="mood-caption">
                  <span className="small-spark">
                    <Sparkle size={16} />
                  </span>
                  <span>
                    {data.mood.v === null
                      ? "一切感受，都可以慢慢来。"
                      : "此刻的感受，不止一种。"}
                    <br />
                    <small>{"名字和分量由情绪配置决定。"}</small>
                  </span>
                </div>
              </div>
            </div>
          )}
          <div className="card-bottom">
            <span>
              <span className="status-dot" />
              {data.source === "demo" ? "示例状态" : "数据库状态快照"}
            </span>
            <span>
              {data.mood.updatedAt
                ? `${date(data.mood.updatedAt)} ${time(data.mood.updatedAt)} 更新`
                : "等待数据"}
            </span>
          </div>
        </section>
        <div className="status-right">
          <Scene
            scene={data.scene}
            onInfo={() =>
              info(
                "情景帧的保鲜期",
                `情景帧描述 AI 理解的当下。状态用一句自述呈现此刻的感受，由模型自己写下。倒计时来自 expires_at；到期会变灰并标为 stale，不自动续期。\n\n${data.scene.raw ? "当前近场快照原文：\n" + data.scene.raw : "焦点、阶段、状态与转场可以分别缺失，缺失时不会自行推断。"}`,
              )
            }
          />
          <button
            className="checkin-card"
            aria-label="翻阅自评"
            onClick={() => go("records")}
          >
            <div className="checkin-icon">
              <Notebook size={26} />
            </div>
            <div>
              <h3>这一刻的感受</h3>
              <p>翻阅当时选择的情绪、理由和原话。</p>
            </div>
            <ArrowUpRight size={21} />
          </button>
        </div>
      </div>
      <div className="status-lower">
        <section className="recent-memories">
          <SectionHead title="最近，被记起的事">
            <button className="text-button" onClick={() => go("memory")}>
              去记忆里看看 <ArrowRight size={15} />
            </button>
          </SectionHead>
          {entries.slice(0, 2).map((e) => (
            <button className="recent-row" key={e.id} onClick={() => detail(e)}>
              <span className="memory-icon">
                <BookmarkSimple size={20} />
              </span>
              <div>
                <h3>{e.title}</h3>
                <p>
                  {e.channels.join(" / ")}
                  <span>{date(e.at)}</span>
                </p>
              </div>
              <ArrowUpRight size={17} />
            </button>
          ))}
          {!entries.length && <Empty text="还没有可展示的记忆" />}
        </section>
        <section className="growth-card">
          <SectionHead title="每一点，都有被留下">
            <Plant size={23} />
          </SectionHead>
          <div className="growth-stats">
            <div>
              <strong>{data.stats.memories.toLocaleString()}</strong>
              <span>记忆片段</span>
            </div>
            <div>
              <strong>
                {data.stats.today}
                <small> 条</small>
              </strong>
              <span>今日新记忆</span>
            </div>
            <div>
              <strong>
                {reports.length}
                <small> 次</small>
              </strong>
              <span>可见自评</span>
            </div>
          </div>
          <p>
            <span className="fine-dot" />
            {data.source === "demo"
              ? "这里展示的是交互示例"
              : "这是一份只读的记忆快照"}
            <span>慢慢积累，也很好。</span>
          </p>
        </section>
      </div>
    </>
  );
}
function Memory({
  data,
  reports,
  detail,
  go,
  initialQuery,
}: {
  data: Snapshot;
  reports: Report[];
  detail: (e: Entry) => void;
  go: (p: Page, section?: string) => void;
  initialQuery: string;
}) {
  const [tab, setTab] = useState<"timeline" | "recall" | "johari">(
    location.hash.endsWith("/johari") ? "johari" : "timeline",
  );
  const [channel, setChannel] = useState("全部渠道");
  const [range, setRange] = useState("all");
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState(initialQuery);
  const [unknown, setUnknown] = useState(false);
  const [index, setIndex] = useState(0);
  const [quadrant, setQuadrant] = useState("");
  useEffect(() => setQuery(initialQuery), [initialQuery]);
  const merged = useMemo(() => mergeEntries(data.entries), [data.entries]);
  const within = (at: string) =>
    range === "all" ||
    (range === "today"
      ? new Date(at).toDateString() === new Date().toDateString()
      : Date.now() - Date.parse(at) <= 7 * 864e5);
  const entries = merged.filter(
    (e) =>
      (channel === "全部渠道" || e.channels.includes(channel as Channel)) &&
      within(e.at) &&
      (kind === "all" || e.kind === kind) &&
      `${e.title} ${e.body} ${e.tags.join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const recalls = data.recalls.filter(
    (r) =>
      (channel === "全部渠道" || r.channel === channel) &&
      within(r.at) &&
      `${r.query} ${r.items.map((i) => i.title).join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  let previousDate = "";
  return (
    <>
      <div className="page-intro">
        <div>
          <p className="overline">那些走过的片刻</p>
          <h1>记忆，是我们之间的回声。</h1>
          <p>从不同的地方来，在这里连成一条线。</p>
        </div>
        <span className="count-note">
          <Brain size={18} />
          {data.stats.memories.toLocaleString()} 条记忆
        </span>
      </div>
      <div className="tabs" role="tablist" aria-label="记忆视图">
        {[
          ["timeline", "事件与记忆"],
          ["recall", "每轮召回"],
          ["johari", "乔哈里之窗"],
        ].map(([id, name]) => (
          <button
            role="tab"
            aria-selected={tab === id}
            key={id}
            onClick={() => setTab(id as typeof tab)}
          >
            {name}
            {id === "recall" && <span>{data.recalls.length}</span>}
          </button>
        ))}
      </div>
      {tab !== "johari" ? (
        <>
          <div className="filter-bar">
            <label className="search-field">
              <MagnifyingGlass size={18} />
              <input
                aria-label="搜索记忆"
                placeholder="找一句话、一种感受、一段回忆…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query && (
                <button
                  aria-label="清空搜索"
                  className="icon-button"
                  onClick={() => setQuery("")}
                >
                  <X size={15} />
                </button>
              )}
            </label>
            <select
              aria-label="按渠道筛选"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
            >
              {["全部渠道", "企微", "聊天", "论坛", "其他"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
            <select
              aria-label="按时间筛选"
              value={range}
              onChange={(e) => setRange(e.target.value)}
            >
              <option value="all">全部时间</option>
              <option value="today">今天</option>
              <option value="week">最近 7 天</option>
            </select>
            {tab === "timeline" && (
              <select
                aria-label="按类型筛选"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                <option value="all">事件与记忆</option>
                <option value="memory">只看记忆</option>
                <option value="event">只看事件</option>
              </select>
            )}
          </div>
          <div className="memory-content">
            <div>
              {tab === "timeline" ? (
                <div className="timeline">
                  {entries.map((e) => {
                    const d = date(e.at);
                    const heading = d !== previousDate;
                    previousDate = d;
                    return (
                      <div key={e.id}>
                        {heading && (
                          <div className="timeline-day">
                            <span />
                            {d}
                            <small>{new Date(e.at).getFullYear()}</small>
                          </div>
                        )}
                        <button
                          className="timeline-entry"
                          onClick={() => detail(e)}
                        >
                          <div className="timeline-time">
                            {time(e.at)}
                            <span
                              className={
                                e.kind === "memory"
                                  ? "memory-node"
                                  : "event-node"
                              }
                            />
                          </div>
                          <div className="timeline-body">
                            <div className="entry-meta">
                              {e.channels.map((c) => (
                                <Source key={c} channel={c} />
                              ))}
                              {e.channels.length > 1 && (
                                <span className="merged-label">
                                  <Check size={12} />
                                  跨渠道已合并
                                </span>
                              )}
                              <span className="entry-type">
                                {e.kind === "memory" ? "记忆片段" : "对话事件"}
                              </span>
                            </div>
                            <h3>{e.title}</h3>
                            <p>{e.body}</p>
                            <div className="tags">
                              {e.tags.map((t) => (
                                <span key={t}>#{t}</span>
                              ))}
                              {e.emotion && (
                                <span className="emotion-mini">
                                  {e.emotion}
                                </span>
                              )}
                            </div>
                          </div>
                          <ArrowUpRight size={17} />
                        </button>
                      </div>
                    );
                  })}
                  {!entries.length && <Empty text="这段时间，暂时没有找到" />}
                  {entries.length > 0 && (
                    <p className="timeline-end">先看到这里，故事还在继续。</p>
                  )}
                </div>
              ) : (
                <div className="recall-list">
                  {recalls.map((r) => (
                    <article className="card recall-card" key={r.id}>
                      <div className="entry-meta">
                        <Source channel={r.channel} />
                        <span>
                          {date(r.at)} {time(r.at)}
                        </span>
                        <Chip>{r.items.length} 条召回</Chip>
                      </div>
                      <h3>{r.query || "一次新的对话"}</h3>
                      <p className="muted">这轮对话实际返回的记忆条目</p>
                      {r.items.map((item) => (
                        <button
                          key={item.id}
                          className="recall-item"
                          onClick={() =>
                            detail(
                              merged.find((e) => e.id === item.id) || {
                                id: item.id,
                                title: item.title,
                                body: item.reason,
                                at: r.at,
                                channels: [r.channel],
                                kind: "memory",
                                tags: [],
                              },
                            )
                          }
                        >
                          <BookmarkSimple size={19} />
                          <div>
                            <b>{item.title}</b>
                            <small>{item.reason || "召回日志未提供理由"}</small>
                          </div>
                          <CaretRight size={17} />
                        </button>
                      ))}
                    </article>
                  ))}
                  {!recalls.length && <Empty text="没有符合条件的召回记录" />}
                </div>
              )}
            </div>
            <aside className="memory-aside">
              <div className="aside-mark">
                <Brain size={32} />
              </div>
              <h3>回忆不止一个入口</h3>
              <p>
                企微里的对话、聊天里的日常、论坛里的发现，都可以属于同一段记忆。
              </p>
              <div className="source-legend">
                {["企微", "聊天", "论坛"].map((c) => (
                  <div key={c}>
                    <Source channel={c} />
                    <span>
                      {
                        merged.filter((e) => e.channels.includes(c as Channel))
                          .length
                      }{" "}
                      条可见
                    </span>
                  </div>
                ))}
              </div>
              <div className="aside-note">
                <Info size={17} />
                <p>
                  有共同证据的片段合并显示，原始来源仍然保留。相似的话不会被直接当成同一件事。
                </p>
              </div>
              <button className="text-button" onClick={() => setTab("johari")}>
                推开乔哈里之窗 <ArrowRight size={15} />
              </button>
            </aside>
          </div>
        </>
      ) : (
        <div className="johari-section">
          <div className="johari-intro">
            <h2>我们知道的，以及还不知道的。</h2>
            <p>一扇关于理解的窗。每多一点记忆，开放的地方就再大一点。</p>
          </div>
          <div className="johari-labels">
            <span>观察者知道的</span>
            <span>观察者还不知道的</span>
          </div>
          <div
            className="johari-grid"
            style={{
              gridTemplateColumns: `${Math.min(1.8, 1 + Math.log10(1 + data.stats.memories) / 5)}fr 1fr`,
            }}
          >
            <button
              className="johari-cell open-area"
              onClick={() => setTab("timeline")}
            >
              <span className="quadrant-label">
                开放区 <ArrowUpRight size={20} />
              </span>
              <strong>被我们共同记住</strong>
              <p>
                {data.stats.memories.toLocaleString()}{" "}
                个记忆片段，让理解慢慢长大。
              </p>
              <div className="window-motif">
                <i />
                <i />
                <i />
                <i />
              </div>
              <small>彼此都知道的部分</small>
            </button>
            <button
              className="johari-cell hidden-area"
              onClick={() => go("records")}
            >
              <span className="quadrant-label">
                隐藏区 <ArrowUpRight size={20} />
              </span>
              <strong>未说出口的感受</strong>
              <p>{reports.length} 次自评，保留它当时的自述。</p>
              <Quotes size={35} />
              <small>自己知道，外部未必知道</small>
            </button>
            <button
              className="johari-cell blind-area"
              onClick={() => setQuadrant("blind")}
            >
              <span className="quadrant-label">
                盲目区 <ArrowUpRight size={20} />
              </span>
              <strong>另一个视角里的它</strong>
              <p>{data.impressions[0]?.theme || "等待第一份整日印象"}</p>
              <small>外部的观察，也许自己还未察觉</small>
            </button>
            <button
              className="johari-cell unknown-area"
              onClick={() => setUnknown(true)}
            >
              <div>
                <span className="quadrant-label">未知区</span>
                <strong>还没被照亮的地方</strong>
                <p>没有目的地，也可以随便翻翻。</p>
                <span className="door-link">
                  推门进去 <ArrowRight size={17} />
                </span>
              </div>
              <div className="door-art" aria-hidden="true">
                <div />
              </div>
            </button>
          </div>
          <p className="johari-foot">这是一种浏览隐喻，不进行心理诊断。</p>
        </div>
      )}
      {unknown && (
        <Modal title="随便翻翻，偶遇一点什么" onClose={() => setUnknown(false)}>
          <div className="unknown-modal">
            <DoorOpen size={38} />
            {data.unknown.length ? (
              <>
                <p>{data.unknown[index % data.unknown.length].text}</p>
                <small>
                  {date(data.unknown[index % data.unknown.length].at)}{" "}
                  留下的一点未尽之意
                </small>
                <button
                  className="button primary"
                  onClick={() => setIndex((i) => i + 1)}
                >
                  <ArrowClockwise size={17} />
                  再翻一页
                </button>
              </>
            ) : (
              <Empty
                text="门后暂时还是一片空白"
                detail="新的未决想法出现时，会留在这里。"
              />
            )}
          </div>
        </Modal>
      )}
      {quadrant && (
        <Modal title="另一个视角的整日印象" onClose={() => setQuadrant("")}>
          <div className="modal-content">
            {data.impressions[0] ? (
              <>
                <Chip>{data.impressions[0].day}</Chip>
                <h3>{data.impressions[0].theme}</h3>
                <p>{data.impressions[0].summary}</p>
                <button
                  className="button soft"
                  onClick={() => go("records", "daily")}
                >
                  去补上我的视角 <ArrowRight size={16} />
                </button>
              </>
            ) : (
              <Empty text="还没有每日印象" />
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
function Records({
  data,
  reports,
  notify,
}: {
  data: Snapshot;
  reports: Report[];
  notify: (s: string) => void;
}) {
  const [tab, setTab] = useState(
    location.hash.endsWith("/daily") ? "daily" : "self",
  );
  const [selected, setSelected] = useState(data.impressions[0]?.day || "");
  const [notes, setNotes] = useState<Record<string, string>>({});
  useEffect(() => {
    let mounted = true;
    api.getDailyNotes().then((n) => {
      if (mounted) {
        setNotes(n);
        setDraft(n[selected] || "");
      }
    });
    return () => {
      mounted = false;
    };
  }, []);
  const [draft, setDraft] = useState(notes[selected] || "");
  const [editing, setEditing] = useState(false);
  const impression = data.impressions.find((i) => i.day === selected);
  const persist = async () => {
    try {
      const next = await api.saveDailyNote(selected, draft.trim());
      setNotes(next);
      setEditing(false);
      notify("补充已保存在这台设备，没有写入记忆库。");
    } catch {
      notify("本地存储不可用，文字仍保留在编辑框中。");
    }
  };
  return (
    <>
      <div className="page-intro">
        <div>
          <p className="overline">留下感受，也留下来处</p>
          <h1>每一刻，都有来处。</h1>
          <p>自己选择的情绪，和当时写下的理由。</p>
        </div>
      </div>
      <div className="tabs" role="tablist" aria-label="记录视图">
        <button
          role="tab"
          aria-selected={tab === "self"}
          onClick={() => setTab("self")}
        >
          情绪自述
        </button>
        <button
          role="tab"
          aria-selected={tab === "daily"}
          onClick={() => setTab("daily")}
        >
          每日印象
        </button>
      </div>
      {tab === "self" ? (
        <div className="records-layout">
          <div className="journal-list">
            {reports.map((r, i) => (
              <article key={r.id} className="journal-entry">
                <div className="journal-date">
                  <strong>{date(r.at)}</strong>
                  <span>{time(r.at)}</span>
                  <i />
                </div>
                <div className="journal-paper">
                  <div className="section-head">
                    <div className="journal-emotion">
                      <span className={`mood-swatch swatch-${i % 3}`} />
                      <h2>{r.label}</h2>
                      <Chip>自述</Chip>
                    </div>
                    <span className="va-small">
                      v {signed(r.v)}
                      <span />a {signed(r.a)}
                    </span>
                  </div>
                  <p>{r.reason}</p>
                  <blockquote>
                    <Quotes size={18} />
                    {r.quote || "这一次，没有引用原话。"}
                  </blockquote>
                </div>
              </article>
            ))}
            {!reports.length && (
              <Empty
                text="还没有留下自评"
                detail="AI 产生自评后，这里会显示它选择的情绪、v/a、理由与原话。"
              />
            )}
          </div>
          <aside className="journal-aside">
            <Notebook size={30} />
            <h3>数字之外，是当时的自述。</h3>
            <p>v 是愉悦程度，a 是唤醒程度。它们只是坐标，不是对感受的评判。</p>
            <div className="scale-legend">
              <span>效价 v</span>
              <div />
              <p>
                <span>不愉悦 -1</span>
                <span>愉悦 +1</span>
              </p>
            </div>
            <div className="scale-legend arousal">
              <span>唤醒 a</span>
              <div />
              <p>
                <span>低唤醒 -1</span>
                <span>高唤醒 +1</span>
              </p>
            </div>
            <small>
              模型自述与当前状态分别记录。
              <br />
              这里保留它自己写下的内容。
            </small>
          </aside>
        </div>
      ) : (
        <>
          <div className="daily-toolbar">
            <label>
              <CalendarBlank size={18} />
              <select
                aria-label="选择每日印象日期"
                value={selected}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setDraft(notes[e.target.value] || "");
                  setEditing(false);
                }}
              >
                {data.impressions.map((d) => (
                  <option key={d.day} value={d.day}>
                    {d.day}
                  </option>
                ))}
              </select>
            </label>
            <span>同一天，两种视角。</span>
          </div>
          {impression ? (
            <>
              <h2 className="daily-title">{impression.theme}</h2>
              <div className="daily-grid">
                <article className="daily-perspective worker-perspective">
                  <span className="perspective-icon">
                    <Sparkle size={24} />
                  </span>
                  <div className="perspective-title">
                    <h3>当日印象</h3>
                    <Chip>{impression.source}</Chip>
                  </div>
                  <p>{impression.summary}</p>
                  <footer>整理一天，也记下它眼里的变化。</footer>
                </article>
                <article className="daily-perspective mine-perspective">
                  <span className="perspective-icon">
                    <Notebook size={24} />
                  </span>
                  <div className="perspective-title">
                    <h3>你的补充</h3>
                    <Chip>你的视角</Chip>
                  </div>
                  {editing ? (
                    <>
                      <label htmlFor="daily-note">补充今天的感受</label>
                      <textarea
                        id="daily-note"
                        value={draft}
                        maxLength={4000}
                        onChange={(e) => setDraft(e.target.value)}
                        rows={7}
                        placeholder="补充你观察到、AI 可能没注意的部分…"
                      />
                      <div className="form-actions">
                        <button
                          className="button soft"
                          onClick={() => {
                            setDraft(notes[selected] || "");
                            setEditing(false);
                          }}
                        >
                          取消
                        </button>
                        <button className="button primary" onClick={persist}>
                          保存补充
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <p className={notes[selected] ? "" : "placeholder-copy"}>
                        {notes[selected] ||
                          "这里留给人的观察与补充，和 AI 的印象分开记录。"}
                      </p>
                      <button
                        className="button soft"
                        onClick={() => setEditing(true)}
                      >
                        <Plus size={16} />
                        {notes[selected] ? "编辑我的补充" : "补上我的视角"}
                      </button>
                    </>
                  )}
                  <footer>保存在本机，随时可以修改。</footer>
                </article>
              </div>
            </>
          ) : (
            <Empty
              text="还没有每日印象"
              detail="记忆库产生整日印象后，可以在这里对照与补充。"
            />
          )}
        </>
      )}
    </>
  );
}

function SnapshotFreshness({
  expiresAt,
  refresh,
}: {
  expiresAt: string | null;
  refresh: () => void;
}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  if (
    !expiresAt ||
    Date.parse(expiresAt) > now ||
    !Number.isFinite(Date.parse(expiresAt))
  )
    return null;
  return (
    <div className="stale-banner" role="status">
      <Clock size={15} />
      这是一份旧快照，等待下一次更新。<button onClick={refresh}>刷新</button>
    </div>
  );
}
function Settings({
  data,
  theme,
  setTheme,
  notify,
}: {
  data: Snapshot;
  theme: string;
  setTheme: (s: string) => void;
  notify: (s: string) => void;
}) {
  const stats = data.stats;
  const total = stats.done + stats.pending + stats.failed;
  const done = total ? Math.round((stats.done / total) * 100) : 0;
  return (
    <>
      <div className="page-intro">
        <div>
          <p className="overline">让一切清清楚楚</p>
          <h1>照看记忆的生长。</h1>
          <p>数据的来处，和它运转的方式。</p>
        </div>
      </div>
      <div className="settings-grid">
        <div className="settings-main">
          <section className="card settings-card">
            <SectionHead title="记忆库概览">
              <Database size={21} />
            </SectionHead>
            <div className="database-stats">
              {[
                ["原始事件", stats.events],
                ["记忆条目", stats.memories],
                ["召回记录", stats.recalls],
                ["每日印象", stats.impressions],
              ].map(([l, v]) => (
                <div key={l}>
                  <strong>{Number(v).toLocaleString()}</strong>
                  <span>{l}</span>
                </div>
              ))}
            </div>
            {!stats.memories && (
              <p className="muted">还没有数据，第一段记忆会从这里开始。</p>
            )}
            <details className="data-explainer">
              <summary>
                这些数字代表什么？
                <CaretRight size={16} />
              </summary>
              <dl>
                <dt>原始事件</dt>
                <dd>来自不同渠道的原始证据；合并展示不会删除来源。</dd>
                <dt>记忆条目</dt>
                <dd>经过整理的摘要、内容、时间与证据引用。</dd>
                <dt>召回记录</dt>
                <dd>每轮对话实际取回的记忆，候选条目另行区分。</dd>
                <dt>向量投影</dt>
                <dd>用来帮助检索的索引，可以从权威记忆重建。</dd>
              </dl>
            </details>
            <p className="field-help">
              {data.source === "demo"
                ? "当前为 mock 数据，未连接真实记忆库。"
                : `数据更新于 ${date(data.capturedAt)} ${time(data.capturedAt)}`}{" "}
            </p>
          </section>
          <section className="card settings-card">
            <SectionHead title="整理进度">
              <Chip className="green">
                {!total
                  ? "等待片段"
                  : stats.pending
                    ? "慢慢整理中"
                    : "本轮已整理"}
              </Chip>
            </SectionHead>
            {total ? (
              <>
                <div className="progress-title">
                  <span>让片段成为记忆</span>
                  <b>{done}%</b>
                </div>
                <progress value={done} max={100} aria-label="任务处理进度" />
                <div className="job-counts">
                  <span>已完成 {stats.done}</span>
                  <span>待处理 {stats.pending}</span>
                  <span>失败 {stats.failed}</span>
                </div>
                <div className="index-progress">
                  <Database size={18} />
                  <div>
                    <b>向量投影</b>
                    <span>
                      {stats.projected} / {stats.projectionTotal} 条已同步
                    </span>
                  </div>
                  <span>
                    {stats.projectionTotal
                      ? Math.round(
                          (stats.projected / stats.projectionTotal) * 100,
                        )
                      : 0}
                    %
                  </span>
                </div>
              </>
            ) : (
              <Empty
                text="还没有需要整理的片段"
                detail="新的事件到来后，可以在这里看到整理进度。"
              />
            )}
          </section>
          <WorkerSettings notify={notify} />
        </div>
        <aside className="settings-aside">
          <section className="card settings-card">
            <SectionHead title="阅读的光线" />
            <div className="theme-options">
              {[
                ["light", "浅色", Sun],
                ["dark", "深色", Moon],
                ["system", "跟随系统", SlidersHorizontal],
              ].map(([id, label, Icon]) => (
                <button
                  className={theme === id ? "active" : ""}
                  key={id as string}
                  onClick={() => setTheme(id as string)}
                  aria-pressed={theme === id}
                >
                  <Icon size={18} />
                  {label as string}
                </button>
              ))}
            </div>
          </section>
          <section className="settings-footnote">
            <ShieldCheck size={23} />
            <h3>只属于这台设备</h3>
            <p>
              人的每日补充和模型设置只存本地。清理浏览器数据也会清除它们。演示不会对外发送
              API Key。
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
function LoadingPage({ page }: { page: Page }) {
  return (
    <div className="loading-page" aria-label="正在加载" role="status">
      <div className="skeleton sk-overline" />
      <div className="skeleton sk-heading" />
      <div className="skeleton sk-subtitle" />
      <div className="card skeleton-card">
        {page === "status" ? (
          <div className="skeleton sk-ring" />
        ) : (
          <>
            <div className="skeleton sk-line" />
            <div className="skeleton sk-line" />
            <div className="skeleton sk-line short" />
          </>
        )}
        <div className="skeleton sk-line" />
        <div className="skeleton sk-line short" />
      </div>
      <div className="card skeleton-card">
        <div className="skeleton sk-line" />
        <div className="skeleton sk-line short" />
        <div className="skeleton sk-line" />
      </div>
      <span className="sr-only">正在把记忆带回来</span>
    </div>
  );
}
export default function App() {
  const [page, setPage] = useState<Page>(getPage);
  const [data, setData] = useState<Snapshot | null>(null);
  const [config, setConfig] = useState<EmotionConfig | null>(null);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [info, setInfo] = useState<{ title: string; body: string } | null>(
    null,
  );
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [theme, setThemeState] = useState(api.getTheme);
  const request = useRef(0);
  const load = async () => {
    const id = ++request.current;
    setLoading(true);
    setError("");
    try {
      const [snapshot, cfg] = await Promise.all([
        api.getSnapshot(),
        api.getConfig(),
      ]);
      if (id !== request.current) return;
      setData(snapshot);
      setConfig(cfg);
    } catch (e) {
      if (id === request.current)
        setError(e instanceof Error ? e.message : "记忆暂时没有回来。");
    } finally {
      if (id === request.current) setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, []);
  useEffect(() => {
    const fn = () => setPage(getPage());
    addEventListener("hashchange", fn);
    return () => removeEventListener("hashchange", fn);
  }, []);
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () =>
      (document.documentElement.dataset.theme =
        theme === "system" ? (media.matches ? "dark" : "light") : theme);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => {
    if (toast) {
      const id = setTimeout(() => setToast(""), 4500);
      return () => clearTimeout(id);
    }
  }, [toast]);
  const go = (p: Page, section?: string) => {
    location.hash = p + (section ? "/" + section : "");
    setPage(p);
    window.scrollTo({ top: 0, behavior: "instant" });
  };
  const setTheme = (s: string) => {
    setThemeState(s);
    try {
      api.saveTheme(s);
    } catch {
      setToast("外观已切换，偏好未能保存。");
    }
  };
  const reports = [...(data?.reports || [])].sort(
    (a, b) => Date.parse(b.at) - Date.parse(a.at),
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <header className="app-header">
        <button
          className="brand"
          aria-label="薪火首页"
          onClick={() => go("status")}
        >
          <span className="brand-icon">
            <Flame weight="fill" size={24} />
          </span>
          <strong>薪火</strong>
          <span className="brand-description">记忆观察室</span>
        </button>
        <div className="header-actions">
          <button className="data-mode" onClick={() => go("settings")}>
            {data?.source === "live" ? "已连接" : "MOCK"}
          </button>
          <button
            className="avatar"
            aria-label="你的设置"
            onClick={() => go("settings")}
          >
            <SlidersHorizontal size={19} />
          </button>
        </div>
      </header>
      <main id="main-content" className="main-content" tabIndex={-1} key={page}>
        {data && !loading && !error && (
          <SnapshotFreshness expiresAt={data.expiresAt} refresh={load} />
        )}
        {loading ? (
          <LoadingPage page={page} />
        ) : error ? (
          <div className="error-state">
            <WarningCircle size={38} />
            <h1>记忆暂时没有回来</h1>
            <p>{error}</p>
            <button className="button primary" onClick={() => load()}>
              再试一次
            </button>
          </div>
        ) : data && config ? (
          <>
            {page === "status" && (
              <Status
                data={data}
                config={config}
                reports={reports}
                go={go}
                detail={setSelected}
                info={(title, body) => setInfo({ title, body })}
              />
            )}{" "}
            {page === "memory" && (
              <Memory
                data={data}
                reports={reports}
                detail={setSelected}
                go={go}
                initialQuery=""
              />
            )}{" "}
            {page === "records" && (
              <Records data={data} reports={reports} notify={setToast} />
            )}{" "}
            {page === "settings" && (
              <Settings
                data={data}
                theme={theme}
                setTheme={setTheme}
                notify={setToast}
              />
            )}
          </>
        ) : null}
      </main>
      <footer className="app-foot">
        <Flame size={12} />
        <span>一起，把日子过成记忆。</span>
      </footer>
      <nav className="bottom-nav" aria-label="主导航">
        {pages.map(([id, label, Icon]) => (
          <button
            key={id}
            className={page === id ? "active" : ""}
            aria-current={page === id ? "page" : undefined}
            onClick={() => go(id)}
          >
            <Icon size={23} weight={page === id ? "fill" : "regular"} />
            <span>{label}</span>
            {page === id && <span className="nav-indicator" />}
          </button>
        ))}
      </nav>
      {toast && (
        <div className="toast" role="status">
          <Check size={18} />
          {toast}
        </div>
      )}
      {selected && (
        <Modal title="一段记忆的来处" onClose={() => setSelected(null)}>
          <article className="memory-detail">
            <div className="entry-meta">
              {selected.channels.map((c) => (
                <Source key={c} channel={c} />
              ))}
              <span>
                {date(selected.at)} {time(selected.at)}
              </span>
            </div>
            <h3>{selected.title}</h3>
            <p>{selected.body}</p>
            {selected.quote && (
              <blockquote>
                <Quotes size={19} />
                {selected.quote}
              </blockquote>
            )}
            <div className="tags">
              {selected.tags.map((t) => (
                <span key={t}>#{t}</span>
              ))}
            </div>
            <footer>
              {selected.channels.length > 1
                ? "已合并跨渠道证据，保留全部来源。"
                : "保留原始来源，不把推测写成事实。"}
            </footer>
          </article>
        </Modal>
      )}
      {info && (
        <Modal title={info.title} onClose={() => setInfo(null)}>
          <div className="modal-content pre-line">{info.body}</div>
        </Modal>
      )}
    </div>
  );
}
