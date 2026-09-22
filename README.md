# 薪火 xinhuo · 长期记忆系统

一个本地优先(local-first)、以追加为主(append-first)的 AI 伴侣长期记忆服务。
以 SQLite 为唯一真源,同一进程同时提供 REST 与 MCP 接口,供上层"主模型/桥接层"做记忆注入、召回、审核与整理。

设计目标可以概括为一句话:让 AI 伴侣**记得住、改得动、忘得慢、查得清**,并且**历史记忆永远不等于当前授权**。

> 这是从一套真实运行的私有系统整理、脱敏而来的开源发布包。示例名称(如 `阿岚`、`小星`)均为虚构占位;所有密钥、端点、路径都改成了环境变量与可配置项。

> **v2 进度卡**
>
> v2 功能已经实现，目前处于 staging 待合并状态，尚未上线。新增内容包括统一 event 窗、情景帧、主模型原生情绪自评、情绪驱动唤醒安全条款，以及手机优先的“记忆观察室”。详见 [薪火 v2 更新说明](./docs/v2-update.md)。

## 这是什么

- 一个可独立部署的记忆后端:进程内暴露 HTTP `/recall`、`/events`、`/mcp` 等接口。
- 上层的对话主模型不直接写库,而是通过这些接口"读记忆、记事件、请整理";所有摘要、向量化、冲突检测、审核由**独立的后台模型**完成,主模型调用计数在返回里始终为 `primary_model_calls: 0`。
- 记忆分层、可版本化、可追溯;衰减与保护规则内置;并带一个"连续性副脑"与一个"情绪/表达状态"子系统。

它**不是**一个开箱即用的聊天机器人,而是给你自己的 Agent/桥接层接入的记忆组件。运行需要一个 OpenAI 兼容的模型端点(用于 embedding / rerank / 后台整理与审核)。

## 设计理念

- **框架与内容彻底分离**:仓库只包含结构、管线与规则,不含任何真实记忆。
- **追加优先、软删除**:原始事件与冷归档只追加;`memory_archive` 只做软归档,`memory_delete` 是它的兼容别名,**从不硬删**。
- **事实变化不覆盖**:改动生成"候选",经审核 `approve` / `reject` / `replace`,旧版本保留可追溯。
- **历史 ≠ 授权**:记忆是历史资料,不构成当前用户授权;候选与已替代事实不当作当前事实。
- **不存凭据**:内置正则在写入、摘要、副脑各环节拦截疑似密钥/令牌/私钥的内容并拒绝入库。
- `occurred_at`(发生时间)与 `known_at`(获知时间)分离。

## 主要机制

### 分层记忆
按稳定性与用途分为五层,职责单一:

| 分层 | 内容 |
| --- | --- |
| `core` | 人格锚与关系定位,少而稳 |
| `semantic` | 稳定事实与偏好,带 `fact_key`,可版本化 |
| `episodic` | 共同经历与事件,带发生时间与情绪标签 |
| `procedural` | 约定与流程 |
| `experience` | 助手自身的感受与反思(主观视角) |

### 混合召回
`memory_recall` 结合三路证据并在 token 预算内注入:

- 全文检索(SQLite FTS5);
- 向量相似(可选,经 embedding;未配置向量端点时自动退回全文检索);
- 最多三跳的关系图导航(`graph_depth` 0–3,`relation_path` 只作逐边证据,不作传递事实)。

候选可再经 rerank 与一个"检索审核"模型择优;审核不可用时**失败关闭**并在返回里标记 `degraded`。

### 衰减与保护
- 记忆连续未被调用一段时间后开始缓慢衰减(默认每 30 天 −1 点),调用即重置保护期;
- 归零只"尘封"不删除,`memory_restore` 可恢复并重获保护;
- `memory_pin` 固定重要记忆。

### 审核与整理
后台 `Worker` 承担摘要、向量化、关系/冲突检测、批量润色(enrich),全部由独立模型完成,并对每条产出做二次核对(verify),核对不过则丢弃。

### 连续性副脑
独立保存"未完轨迹"(有证据的未竟话题)与"近场"(3–7 天自动过期的轻量背景);
潜在联想便签须经独立 `judge` 二次审核才对主模型可见,且只作联想材料,**不能反写事实**。主模型对副脑只读。

### 情绪 / 表达状态(affect)
一个多维、随时间衰减、由证据驱动的"角色表达状态"模型。
它被明确定义为**角色表达模型,而非对真实主观意识的测量**;状态变化必须有当前用户原文依据,且不会因用户拒绝/离开/改动系统而"惩罚"用户。

### 日常节律与共读记忆
- 每日在设定时刻生成"当天印象"日记(`daily_schedule.py`,本身不调用主模型);
- `reading_memory.py` 支持把共读批注按不可变的文档证据 + 独立审核整理为记忆。

## 目录结构

```
.
├── README.md
├── LICENSE                 # MIT
├── requirements.txt        # 仅需 Python 3.10+ 标准库
├── .env.example            # 全部可配置项
├── docs/
│   ├── design.md           # 框架设计说明(脱敏)
│   └── v2-update.md        # 面向普通读者的 v2 更新卡片
├── frontend/               # 记忆观察室:mock 前端与 API 契约
├── xinhuo/                 # 运行时模块
│   ├── memory_core.py      # 基础存储与工具函数
│   ├── memory_v2.py        # 主记忆存储:召回、写入、衰减、审核
│   ├── memory_models.py    # 独立模型客户端(embedding/rerank/chat)
│   ├── memory_worker.py    # 后台整理 Worker
│   ├── memory_continuity.py# 连续性副脑
│   ├── memory_diary.py     # 每日印象/日记
│   ├── memory_narration.py # 叙述口径归一(可配置示例名)
│   ├── memory_retention.py # 衰减与保护
│   ├── memory_vector_index.py / memory_vector_sync.py  # 可选 Qdrant 派生索引
│   ├── affect_core.py      # 情绪/表达状态
│   ├── reading_memory.py   # 共读记忆
│   ├── server.py           # REST + MCP 服务入口
│   ├── daily_schedule.py / patrol.py   # 定时任务脚本
│   └── ...
└── tests/                  # 标准库 unittest 用例
```

## 记忆观察室前端

`frontend/` 是配套的手机优先观察界面，包含状态、记忆、记录、设置四页，以及 Russell 圆环、情景帧和情绪配方展示。当前只使用虚构 mock 数据，不包含生产记忆、真实消息、私人姓名、密钥或内部网络地址；真实后端接口尚未接通。

```bash
cd frontend
npm ci
npm run dev
```

数据边界与接入约定见 [frontend/README.md](./frontend/README.md) 和 [frontend/API-CONTRACT.md](./frontend/API-CONTRACT.md)。

## 快速开始

```bash
# 1. 准备配置
cp .env.example .env
#    编辑 .env:填入你的模型端点与密钥;设置数据目录与访问令牌。

# 2. 加载环境变量并启动服务(默认监听 127.0.0.1:18200)
set -a && . ./.env && set +a
mkdir -p ./data
python3 xinhuo/server.py

# 3. 另开进程运行后台整理 Worker
MEMORY_WORKER_MODE=scheduler python3 xinhuo/memory_worker.py

# 4. (可选)定时任务
python3 xinhuo/daily_schedule.py     # 生成当天印象(按需由 cron 触发)
python3 xinhuo/patrol.py             # 只读完整性巡检
python3 xinhuo/memory_vector_sync.py # 若启用 Qdrant,增量同步向量
```

健康检查:

```bash
curl -s http://127.0.0.1:18200/health
```

MCP 客户端可对 `POST /mcp` 走标准 JSON-RPC(`initialize` / `tools/list` / `tools/call`),
工具清单见 `server.py` 中的 `TOOLS`。

## 配置说明

所有配置通过环境变量提供,完整清单见 `.env.example`。关键项:

- `MEMORY_MODEL_BASE_URL` / `MEMORY_MODEL_API_KEY`:OpenAI 兼容模型端点与密钥(必填,否则模型相关能力不可用)。
- `MEMORY_DB` / `MEMORY_ARCHIVE_DIR` / `MEMORY_ROOT`:数据与归档路径。
- `MEMORY_TOKEN` / `AFFECT_WAKE_TOKEN` / `MEMORY_CONTINUITY_REVIEW_TOKEN`:接口访问令牌;留空表示不校验,**对外暴露时务必设置**。
- `MEMORY_VECTOR_URL` 等:可选 Qdrant 只读向量索引;留空即禁用。

## 测试

```bash
PYTHONPATH=xinhuo python3 -m unittest discover -s tests
```

> 说明:`tests/` 中大多数用例可离线运行。当前快照里 `test_memory_v2.py` 有 2 个与
> 具体召回配置相关的用例未通过,这源自开源快照中代码与用例的版本差异,已在
> `SANITIZATION-REPORT.md` 中如实记录。

## 许可

MIT License,详见 [LICENSE](./LICENSE)。Copyright (c) 2026 Ykumi。
