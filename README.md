# 薪火 xinhuo · 记忆观察室 v2
暂不推荐使用，bug太多
可独立部署的长期记忆库，配套手机优先的状态、记忆、记录、设置四页。部署后输入访问 Token，在网页填写独立工作模型的 API 地址、API Key 与模型 ID，即可开始保存和整理记忆。

SQLite 是唯一真源；原始事件追加保存，事实变更进入候选审核，归档保留历史。REST 与 MCP 可供自己的 Agent 使用。它提供记忆和表达状态，不自带聊天主模型，也不会自行发消息。

## 开始使用

### 本机运行（Python 3.10+、Node.js 24+）

```bash
git clone https://github.com/meixi223-glitch/xinhuo-memory.git
cd xinhuo-memory
./scripts/start.sh
```

启动脚本生成 `data/access-token`、安装并构建前端，随后同时启动 HTTP 服务和持久后台工人。已有 Token 与数据库不会被覆盖。打开 [本机观察室](http://127.0.0.1:18200)，从本机 `data/access-token` 文件复制 Token 登录。

### Docker Compose

```bash
python3 scripts/init.py --compose
docker compose up -d --build
```

生成的 `.env` 包含访问 Token。Compose 将数据保存到 `xinhuo-data` 持久卷，端口默认仅绑定本机 `127.0.0.1:18200`。详细的域名、HTTPS、备份、升级说明见 [部署指南](docs/deployment.md)。不要执行 `docker compose down -v`，它会删除数据卷。

### 第一次登录后

1. 进入「设置」，分别填写**记忆整理**和**独立复核**的 OpenAI 兼容 API 地址、模型 ID、API Key。本地无鉴权模型服务可留空 Key。
2. 点击保存，配置在下一次模型请求生效。可点击「测试已保存配置」，发送固定测试输入验证接口；该操作可能产生少量模型费用。
3. 在「记忆 → 添加片段与查找记忆」保存事件，后台自动提取、复核并生成情景帧。也可让 Agent 通过 `/events` 或 MCP `memory_ingest` 写入。
4. 嵌入、重排序是可选能力，分别要求 `/embeddings`、`/rerank`；未配置时仍可使用全文检索。召回复核不可用时返回空结果并注明降级。

## 已接通的功能

| 界面 | 实际行为 |
| --- | --- |
| 状态 | 读取衰减后的 Russell 坐标、最近自评变化量、有有效期的情景帧 |
| 记忆 | 分页浏览、全库查找、真实召回、添加原始片段、固定、软归档、候选审核 |
| 记录 | 主模型自己的情绪自述、每日印象、服务端保存的人工补充 |
| 设置 | 后台整理进度、四类真实工人配置、连接测试、复合情绪命名、独立关系维度、唤醒策略 |

首次启动为空库；产品不导入 mock 记录。未收到自评时显示缺失，不拿 0 冒充测量结果。自评中的 `dims` 是 **-0.18～0.18 的变化量**，不会显示成当前百分比强度。关系维度单独保存。

原生情绪由主模型通过 `mood_self_report` / `/affect/self-report` 提交，必须引用已入库的原文；工人不替主模型选择情绪。情景帧由整理工人生成并经独立复核，感受只引用近期主模型自述。历史片段不会被重新赋予新的「现在」。极端高唤醒、低效价时策略返回 `skip_proactive=true`；上层发信系统必须执行该限制。

## Agent 接入

同一服务提供 `POST /mcp` JSON-RPC，以及 `/events`、`/recall`、`/affect/self-report` 等 REST 接口。请求头使用 `Authorization: Bearer <MEMORY_TOKEN>`，不要把 Token 放在 URL。浏览器使用 HttpOnly 会话 Cookie，API Key 只由服务器发送给指定模型端点。

MCP 支持 `initialize`、`tools/list`、`tools/call`。主要工具包括 `memory_ingest`、`memory_recall`、`memory_browse`、`memory_upsert`、`memory_review`、`memory_restore`、`mood_status`、`mood_self_report`、`mood_why`、`mood_composite_rules`。

接口与约束见 [接入契约](frontend/API-CONTRACT.md)、[v2 更新说明](docs/v2-update.md)、[部署指南](docs/deployment.md)。

## 数据与配置

默认 `data/`（容器内 `/data`）包括数据库、归档、`workers.json` 与配置备份。模型密钥以权限 `0600` 保存在服务器文件中，**不是加密存储**；不会在配置读取响应、快照或浏览器 localStorage 中返回。更改已有工人配置前保留精确的时间戳备份。

这是单所有者实例。需要多人隔离时部署多个实例和独立数据卷。网页展示默认 namespace，情景帧是实例级状态；不要把 namespace 当用户权限隔离。

## 验证

```bash
PYTHONPATH=xinhuo python3 -m unittest discover -s tests
npm ci --prefix frontend
npm run build --prefix frontend
cd frontend
npx playwright install chromium
npm test
```

浏览器测试创建临时空库，不连接生产数据。HTTP 集成测试使用本地模拟模型服务，覆盖 Token、Cookie、配置不回传密钥、实际模型路由、事件去重、后台提取与情景帧。现有 Chrome 可通过 `PLAYWRIGHT_CHROME_PATH` 指定。

详见 [验收记录](docs/verification.md)。Python 后端无第三方运行依赖；前端打包依赖固定在 lockfile 中。

## 源码

- `xinhuo/room_runtime.py`：部署入口，运行 HTTP 与工人。
- `xinhuo/room_server.py` / `room_snapshot.py` / `room_config.py`：网页 API、数据映射与配置。
- `xinhuo/event_window.py` / `situation_frames.py` / `affect_core.py`：v2 事件窗、情景帧与原生情绪。
- `xinhuo/memory_*.py`：分层存储、召回、复核、整理、衰减与连续性。
- `frontend/`：React / TypeScript 界面。旧 mock fixture 只用于历史设计参考，生产入口不引用。

MIT License，Copyright (c) 2026 Ykumi。仓库仅含脱敏架构、通用规则和虚构测试数据。
