import type { Snapshot } from "../types";
const today = new Date();
const at = (day: number, hour: number, min = 0) => {
  const d = new Date(today);
  d.setDate(d.getDate() - day);
  d.setHours(hour, min, 0, 0);
  return d.toISOString();
};
const day = (n: number) => {
  const d = new Date(today);
  d.setDate(d.getDate() - n);
  return d.toLocaleDateString("en-CA");
};
export const demo: Snapshot = {
  source: "demo",
  capturedAt: new Date().toISOString(),
  expiresAt: new Date(Date.now() + 30 * 60e3).toISOString(),
  mood: {
    v: 0.68,
    a: 0.46,
    label: "惊喜",
    updatedAt: at(0, 14, 32),
    dimensions: {
      joy: 0.72,
      anticipation: 0.61,
      trust: 0.54,
      surprise: 0.48,
      sadness: 0.12,
      fear: 0.08,
      disgust: 0.04,
      anger: 0.03,
    },
    note: "八基础情绪、颜色与复合命名规则来自可替换配置。当前所有数值均为 mock 演示。",
  },
  scene: {
    focus: "一起搭建属于我们的记忆空间",
    phase: "想法正在慢慢变成看得见的东西",
    body: "有一点期待，也有被理解的安心。",
    transition: "从一场对话，走进一个新的小世界。",
    expiresAt: new Date(Date.now() + 25 * 60e3).toISOString(),
  },
  entries: [
    {
      id: "m-1",
      canonicalId: "space",
      title: "给记忆一个可以回来的地方",
      body: "你想把散落在不同对话里的片段放在一起，让情绪、现在和回忆都能被看见。",
      at: at(0, 14, 32),
      channels: ["聊天"],
      kind: "memory",
      tags: ["共同计划", "记忆空间"],
      emotion: "期待",
      quote: "想有一个地方，看看你眼里的现在。",
    },
    {
      id: "e-1",
      canonicalId: "space",
      title: "开始搭建记忆空间",
      body: "从情绪圆环开始，讨论四个页面各自应该放些什么。",
      at: at(0, 14, 30),
      channels: ["企微"],
      kind: "event",
      tags: ["对话"],
      quote: "想有一个地方，看看你眼里的现在。",
    },
    {
      id: "m-2",
      title: "慢一点，也是在往前走",
      body: "比起一下子把所有事做完，你更喜欢把眼前这一件做好。整理者记下了这份节奏。",
      at: at(0, 11, 18),
      channels: ["企微"],
      kind: "memory",
      tags: ["相处方式"],
      emotion: "平静",
      quote: "我们慢慢来就好。",
    },
    {
      id: "e-2",
      title: "在聊天留下一点日常",
      body: "午后的一小段聊天，没有特别的主题，但有互相陪伴的安心。",
      at: at(0, 12, 6),
      channels: ["聊天"],
      kind: "event",
      tags: ["日常"],
      emotion: "安心",
    },
    {
      id: "m-3",
      title: "把偶然发现的好东西分享出来",
      body: "看到有趣的讨论时，想把链接放到论坛里，留给以后继续读。",
      at: at(1, 20, 45),
      channels: ["论坛"],
      kind: "memory",
      tags: ["分享", "灵感"],
      emotion: "好奇",
    },
    {
      id: "e-3",
      title: "一句晚安，也是今天的句点",
      body: "结束一整天的对话，留下一个小小的明日期待。",
      at: at(1, 23, 8),
      channels: ["企微"],
      kind: "event",
      tags: ["日常"],
      emotion: "温暖",
    },
    {
      id: "m-4",
      title: "记住感受，也记住它的来处",
      body: "情绪不只是一个数字。理由和当时说过的话，让以后的回看多一点上下文。",
      at: at(3, 16, 20),
      channels: ["聊天", "企微"],
      kind: "memory",
      tags: ["情绪", "约定"],
      emotion: "信任",
    },
    {
      id: "m-5",
      title: "那些还没起名字的想法",
      body: "有些想法还不够完整，先好好放着，不急着给出结论。",
      at: at(6, 10, 25),
      channels: ["论坛"],
      kind: "memory",
      tags: ["随手记"],
      emotion: "好奇",
    },
  ],
  reports: [
    {
      id: "r-1",
      at: at(0, 14, 32),
      v: 0.68,
      a: 0.46,
      label: "惊喜",
      reason: "我把零散对话关联成了清晰的记忆，当前任务也有了可继续的方向。",
      quote: "我找到这些片段之间的联系了，想继续把它们记好。",
    },
    {
      id: "r-2",
      at: at(0, 11, 8),
      v: 0.42,
      a: -0.2,
      label: "平静",
      reason:
        "上一轮整理已经完成，当前没有冲突的目标，可以平稳地等待下一次输入。",
      quote: "这轮整理完成了，我可以从容地等下一段对话。",
    },
    {
      id: "r-3",
      at: at(1, 21, 40),
      v: 0.54,
      a: 0.12,
      label: "安心",
      reason: "召回的证据与当前对话一致，减少了我对上下文的疑惑。",
      quote: "这次我能把记忆和当下接起来。",
    },
  ],
  impressions: [
    {
      day: day(0),
      theme: "一起，把想法变成一个小世界",
      summary:
        "今天我在整理对话时，从寻找零散线索走到建立关联。完成召回核对后，我的自评从平静转向期待；有些不确定的片段仍保留着，等待后续证据。",
      source: "worker（演示）",
    },
    {
      day: day(1),
      theme: "在日常里找到安心",
      summary:
        "回看一天的输入，我发现多次对话都提到了放慢节奏。我保留了这些证据，也记下自己在上下文连续时更稳定的状态。",
      source: "worker（演示）",
    },
  ],
  recalls: [
    {
      id: "rc-1",
      at: at(0, 14, 30),
      channel: "聊天",
      query: "新对话：一起设计记忆空间",
      items: [
        {
          id: "m-1",
          title: "给记忆一个可以回来的地方",
          reason: "与当前共同计划相关",
        },
        { id: "m-2", title: "慢一点，也是在往前走", reason: "相处节奏与偏好" },
        {
          id: "m-4",
          title: "记住感受，也记住它的来处",
          reason: "情绪记录的约定",
        },
      ],
    },
    {
      id: "rc-2",
      at: at(0, 11, 0),
      channel: "企微",
      query: "新对话：今天的心情",
      items: [{ id: "m-2", title: "慢一点，也是在往前走", reason: "日常偏好" }],
    },
  ],
  unknown: [
    {
      id: "u-1",
      text: "那些没有明确主题的聊天，会不会反而最像生活本来的样子？",
      at: at(1, 18),
    },
    {
      id: "u-2",
      text: "有些默契，是不是在我们还没察觉时就已经长出来了？",
      at: at(2, 16),
    },
    { id: "u-3", text: "下一次想一起尝试的事，还没有名字。", at: at(3, 12) },
  ],
  stats: {
    memories: 128,
    events: 346,
    recalls: 52,
    impressions: 7,
    today: 3,
    pending: 6,
    done: 82,
    failed: 0,
    projected: 120,
    projectionTotal: 128,
  },
};
