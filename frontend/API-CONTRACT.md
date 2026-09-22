# 真实接入契约

所有网页数据经 `src/api.ts` 访问同源接口。服务端实现位于 `room_server.py`、`room_snapshot.py`、`room_config.py`。

| 方法与路由 | 说明 |
| --- | --- |
| POST `/api/login` `{token}` | 验证 MEMORY_TOKEN，创建 12 小时 HttpOnly / SameSite=Strict 会话 |
| GET `/api/session` | 检查会话，未授权 401 |
| POST `/api/logout` | 撤销当前会话 |
| GET `/api/snapshot` | SQLite 实时快照、最近 100 条历史、首批条目及 nextOffset |
| GET `/api/entries?offset=0&query=` | 全库查找/分页，items 与 nextOffset |
| GET `/api/emotions` | 基础维度及展示配置；复合名称由服务端计算 |
| GET `/api/workers` | 四类角色的真实配置，不返回 Key，仅 hasApiKey |
| POST `/api/workers/{id}` | 保存 endpoint / model / apiKey / provider；Key 留空保留旧值 |
| POST `/api/workers/{id}` `{clearApiKey:true}` | 显式清除指定角色 Key |
| POST `/api/workers/{id}/test` | 使用已保存配置，发送固定输入验证对应接口 |
| GET/POST `/api/notes` | 人工每日补充，POST `{day,text}`；独立于模型自述 |
| GET `/api/candidates` | 最多 100 条候选 |
| GET `/api/composite-rules` | 动态命名规则 |
| POST `/api/events` | 追加原始事件并入持久队列；稳定 source_msg_id 去重 |
| POST `/api/tool` `{name,arguments}` | 限定的记忆写入、召回、核对、固定、归档、恢复及规则编辑 |

网页调用无 namespace 参数；实例服务默认 namespace。不是多用户服务。

## v2 REST / MCP

- GET `/events/window?from=<ISO>&to=<ISO>&channel=`：统一事件窗口，按去重指纹聚合渠道。
- GET `/situation-frames/latest`：`{frame,fresh}`，原始帧含 `generated_at_utc`、`ttl_seconds`、`stale`。前端将生成时间加 TTL 转为绝对 `expiresAt`；过期不续命。
- POST `/situation-frames/refresh`：写入有明确来源的情景帧，原生字段见 `situation_frames.py`。
- POST `/affect/self-report`（MCP `mood_self_report`）：`model`、`valence`/`arousal`、`dims`、独立 `relationships`、`reason`、精确原文 `evidence`、`confidence`、`stated_at`、`turn_id` 或 `source_msg_id`。
- POST `/affect/state`（`mood_status`）、MCP `mood_why`：查看状态或自述。
- POST `/affect/wake-policy`：连续 Russell 策略，包括 `interval_factor`、`skip_proactive`。
- MCP `mood_composite_rules` / `mood_composite_rule_set`：读取/修改命名规则。

REST / MCP 使用 `Authorization: Bearer <MEMORY_TOKEN>`，不使用网页会话或 URL Token。

## 数据语义

`mood.v/a` 来自已衰减内核，未有状态事件时返回 null。`mood.dimensions` 是最近自述的基础情绪增量，保留符号、范围 -0.18～0.18；`dimensionMode=delta`。未提供的维度返回 null。八个基础维度只接受 joy/sadness/fear/anger/surprise/disgust/anticipation/trust。

`relationships` 来自单独的关系状态表；尚未报告时是配置基线，界面明确提示。不能与基础配方混算，也不驱动唤醒频率。

`scene.body` 仅引用近期主模型自己生成的自述，不用用户自己的心情代替。`reports` 只来自 `affect_selfreports`；每日人工补充不进入自述。

`entries.canonicalId` 只使用可信来源身份；相似文字不会自动在时间线合并。`/events/window` 的后端去重指纹视图是单独的窗口能力。`recalls.items` 过滤 `returned=false` 的候选，只显示日志明确实际返回的记忆。

配置保存在服务端，保存成功表示下一次请求将读取新值；连接测试才说明端点接受了真实请求。网络失败、未配置、401、数据为空分别呈现，不回退 mock。
