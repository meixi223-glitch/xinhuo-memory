# 前端与后端的适配约定

这是前端领域模型，不臆造后端路由。后端组员确定真实接口后，只改 `src/api.ts` 中的数据实现。组件消费 TypeScript 对象，不直接依赖供应商响应结构。

| 方法 | 返回 | 当前行为 |
| --- | --- | --- |
| `getSnapshot()` | `Snapshot` | 延迟返回 mock 快照；数据与时间决定显示状态 |
| `getConfig()` | `EmotionConfig` | 返回八维配置及命名规则表 |
| `getDailyNotes()` | `Record<day, text>` | 读取按日期组织的本机补充 |
| `saveDailyNote(day, text)` | `Record<day, text>` | 保存单日补充 |
| `getWorkerProfiles()` | `WorkerProfile[]` | 返回工作清单、各自的候选模型/协议与本机配置 |
| `saveWorkerConfig(workerId, config)` | `void` | 按用途独立保存本机配置，无联网副作用 |
| `clearApiKey(workerId)` | `void` | 只清除该用途的密钥，保留其他用途与字段 |

## 核心字段

- `mood.v` / `mood.a`：范围 -1 到 1，缺失使用 `null`，不能用 0 冒充缺失。
- `mood.dimensions`：按配置 ID 索引，数值范围 0 到 1；不要求分量加起来为 1；缺失维度显示「未提供」。
- `EmotionConfig.dimensions`：`id`、显示名称、颜色。可增减、重排和改名。
- `EmotionConfig.compositeRules`：按顺序匹配阈值条件；匹配不到使用 `fallbackLabel`。可以在适配层改成使用后端返回的 `mood.label`，无需改 UI。
- `scene.body`：界面标签为「状态」，用一句模型自己的感受描述当下，不展示为机器指标清单，也不是人的身体状态。缺失时不推断。
- `reports[]`：模型自己生成的自评，`label`、v/a、`reason` 与 `quote` 都属于模型。由快照返回，不接受人的表单代填；原话按原样展示。
- `expiresAt`：整份快照的绝对过期时间，`null` 表示未指定期限。前端按时间自然显示旧快照提示，不从历史条目的年龄推断。
- `scene.expiresAt`：绝对 ISO 时间；真正过期时卡片变灰。没有帧时返回空字段与 null 时间。
- `entries[].canonicalId`：可信的共同事件/证据身份。只有 ID 相同才合并；聚合渠道、标签，优先记忆内容，保留较新的事件时间。
- `recalls[].items`：实际返回给新对话的条目，不能把所有候选塞进来。每条保留 ID、名称和理由。
- `impressions[].source`：整理来源的显示名称，可为 worker 或人工撰写者；前端不硬推断作者。
- `stats`：完整数据集统计，和当前加载的可见列表数量不同。
- `source`：`demo` 或 `live`，由适配层明确声明数据来源。

## 状态语义

加载时不展示上一份数据伪装成功，使用骨架屏；读取失败显示可重试的错误页。空数据有具体说明。

情景帧根据 `expiresAt` 过期。历史记忆、自评和日记不会因为年代久远而失效；当整份快照过期时给出全局旧快照提示，保留历史内容。没有产品内的状态选择器。测试通过隔离的 mock 模块响应与虚拟时钟验证加载、空、过期、失败和重试。

## 保持边界

- 不将本机保存的 API Key 自动附加到快照、自评、日记、遥测或日志。
- 不将模型配置保存的 UI 成功提示当作线上 worker 已修改。
- 不直接导入生产 SQLite、真实消息或密钥到 mock 文件。
- 真实接口负责鉴权、跨页加载及后端错误转换。当前前端没有启动后台整理、部署、数据库写入或消息发送。
- 每日的「你的补充」仍是人的本地输入，与模型的当日印象分开。若需同步，先定义授权与同步语义。
- 旧 `xinhuo-self-reports` 人工草稿保留在本机，但不会读取为模型自述。
- `WorkerProfile` 清单由适配层给出，含稳定的 `id`、显示名、说明、能力类型、协议选项、模型选项和配置。前端按清单渲染，不假定实际后端只有八种工作。
- 多模型配置存储于 `xinhuo-worker-configs`，按 `workerId` 索引。旧 `xinhuo-model-config` 只归入记忆整理，在首次成功写入新结构后移除旧槽；不向其他用途复制密钥。
