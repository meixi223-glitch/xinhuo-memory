# 脱敏报告 · SANITIZATION-REPORT

> 本报告列出从 `src/` 生成 `dist/` 过程中清除/改写的敏感内容类别,供发布前人工复核。
> 生成方式:只读 `src/`,按固定替换表产出到 `dist/`,未改动任何线上代码。

## 一、来源与产物

- 源:`/srv/agent-collab/work/xinhuo-oss/src/`(28 个文件:26 个 `.py` + `README.md` + `memory-framework-draft.md`)。
- 产物:`/srv/agent-collab/work/xinhuo-oss/dist/`。
- 处理后所有 `.py` 均通过 `python3 -m py_compile`(25 个文件)。

## 二、清除/改写的敏感内容类别

### 1. 内部代号
- `Aelios` / `aelios` / `AELIOS` / `AeliosLocal` / `aelios-local` → 统一改为 `xinhuo` / `Xinhuo` / `XINHUO`。
- 影响:HTTP `server_version`、`/health` 服务名、MCP `serverInfo.name`、启动日志、模块 docstring 等。
- `memory_core.py` docstring 中 "inspired by Aelios/Graphiti/OmniMemory/LMC-5" 去掉自指的 `Aelios`,保留公开项目引用。

### 2. 真实人名 / 昵称 → 中性示例名
- `郁美` → `阿岚`(示例 owner);其罗马字 `Yumi` / `Ykumi` / `meixi` → `Alan` / `alan`。
- `小烬` → `小星`;`沈知烬` → `林小星`;`Xiaojin` → `Xiaoxing`;小写 `xiaojin` → `xinhuo`。
- 版本标识 `NARRATION_VERSION` `yumi-she-v1` → `alan-she-v1`。
- 叙述归一逻辑(`memory_narration.py`)与相关测试同步改名,保持一致、可编译、可运行。
- 说明:owner 示例仍保留"女性/她"的人称归一**功能**(这是特性而非隐私),仅名字换成虚构占位。
- 例外(经确认为作者署名,非泄露):`LICENSE` 与 `README` 的版权行按任务要求保留 `Copyright (c) 2026 Ykumi`。

### 3. 真实 API 端点 / 域名
- 未发现硬编码真实域名或 IP;模型/向量端点原本即通过环境变量注入。
- `.env.example` 中端点值一律为占位域名(`https://your-model-endpoint.example/v1`),并提供 `MODEL_API_BASE` 占位说明。
- 默认监听 `127.0.0.1` 为本机回环地址,予以保留。

### 4. 密钥 / 令牌 / 密码 / 私钥
- 未发现任何硬编码密钥、Bearer 令牌、密码或私钥。
- 所有令牌均来自环境变量(`MEMORY_MODEL_API_KEY`、`MEMORY_TOKEN`、`AFFECT_WAKE_TOKEN`、`MEMORY_CONTINUITY_REVIEW_TOKEN`、`MEMORY_VECTOR_API_KEY`),`.env.example` 中给出空值/占位。
- 代码内的 `SECRET` 正则是**凭据拦截器**(阻止疑似密钥入库),予以保留。

### 5. 企业微信 / webhook / 具体集成标识
- 事件来源标识 `wecom_wake` → `wake`,`wecom_app` → `chat`,其余 `wecom` → `im`。
- 内部代办/门铃系统标识 `doorbell` → `task`(含 `doorbell_completion` → `task_completion`、消息前缀 `[doorbell` → `[task`)。
- 中文串 `企业微信` → `IM 平台`。
- 推理服务商标识 `siliconflow_independent_judge` → `independent_judge`。

### 6. 服务器绝对路径 → 可配置路径
- `/var/lib/aelios-local*` → `./data*`;`/var/lib/reading-nook` → `./data/reading`;`/opt/apps/reading-nook` → `./reading`。
- `daily_schedule.py` 原为硬编码路径,改为读取 `MEMORY_DB` / `MEMORY_ARCHIVE_DIR` 环境变量(默认相对路径)。
- `affect_core.py` 的 `observe_environment` 默认组件字典曾内联三条真实基础设施路径
  (`/root/claude-anthropic-bridge/persona-system.mjs`、`/opt/aelios-local/memory_v2.py`、
  `/root/.config/xiaojin-mcp-servers.json`),已改为空字典 `{}`(由调用方自行传入待监控组件)。

### 7. 供应商/主模型指向(去品牌化)
- "the primary Claude bridge" → "the primary model bridge";"Claude credentials" → "primary-model credentials";
  实体停用词集合中的 `'Claude'` → `'PrimaryModel'`。
- 注释中私有桥接函数名 "the bridge's formatMemoryContext" → "the client's memory formatter"。
- 模型默认名(`BAAI/bge-m3` 等)为公开开源模型标识,作为合理默认值予以保留。

### 8. 个人对话内容 / 示例记忆
- 未发现真实对话记录被写入代码或注释;涉及的中文长串均为**提示词模板/规则**,非真实聊天内容,已随人名替换而中性化。
- 测试中的示例数据(如"绿茶""林舟在湖边捡到铜钥匙"等)为虚构占位,予以保留。

## 三、有意排除的文件(未纳入发布包)

- `migrate_worker.py`:一次性私有迁移脚本,深度绑定旧的 Cloudflare Worker 部署
  (`workers.dev`、`companion-memory`、`/root/xiaojin/proxy.js`、`AELIOS_PROXY_FILE` 等),对开源用户无价值且脱敏风险高。
- `test_daily_wake.py`:依赖 `affect_wake` 模块,该模块不在 `src` 快照内,无法在本包运行。
- `test_reading_memory.py`:依赖 `reading_views` / `reading_mcp` 模块,同样不在 `src` 快照内。

## 四、验证

- 编译:`python3 -m py_compile xinhuo/*.py tests/*.py` → 25 个文件全部通过。
- 残留扫描:对整个 `dist/` 全文检索
  `郁美|小烬|沈知烬|ykumi|meixi|aelios|wecom|企业微信|doorbell|siliconflow|workers.dev|persona-system|proxy.js|/opt/aelios|/root/|xiaojin`
  → 仅 `LICENSE` / `README` 的作者署名 `Ykumi` 命中(有意保留),其余为 0。
- 硬编码密钥扫描(`sk-…` / `bearer …` / `api_key=…`)→ 0 命中。
- 测试:`PYTHONPATH=xinhuo python3 -m unittest discover -s tests` → 46 个用例,44 通过。
  剩余 2 个失败位于 `test_memory_v2.py`(与召回/审核具体配置相关),在**未脱敏的原始 `src`** 上同样以相同断言失败,
  属源快照中代码与用例的版本差异,**非本次脱敏引入**。

## 五、发布前人工复核建议

- 确认示例名 `阿岚` / `小星` 及 owner 的"女性/她"人称设定符合发布意图(如需完全去性别,可进一步调整 `memory_narration.py`)。
- 确认作者署名 `Ykumi` 为期望公开的署名。
- 如需修复 `test_memory_v2.py` 的 2 个失败用例,建议对齐代码与用例版本后单独处理。

## 六、v2 独立部署版补充（2026-09-22）

新增公开 v2 事件窗、情景帧、原生情绪与网页服务。只从授权架构代码中移植实现，不复制生产数据和环境。私有名称改为原公开示例名；私有提示锚依赖移除；环境监控默认空字典。模型与 Token 配置只从环境或部署时生成的权限受限文件读取。

新测试中的 Token / Key 均为明确的 `fixture` 字符串，不是可用凭据。仓库忽略 `.env`、数据卷、配置备份、node_modules 和浏览器测试产物；发布源码包只收录 Git 文件和无私有数据的前端构建。

最新验证覆盖 66 项 Python 测试及 5 项真实后端浏览器测试，全部通过。上文旧快照 44/46 的记录是历史状态，最新情况见 `docs/verification.md`。
