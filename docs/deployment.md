# 独立部署指南

## 运行形态

一个进程同时提供静态前端、同源 API、REST/MCP 与一个后台工人线程。仅部署 `frontend/dist` 无法使用完整功能。默认空库、默认不调用外部模型；配置整理和复核后自动处理队列。语义模型需支持 OpenAI 兼容 `/chat/completions` 与 JSON 输出。本版本不支持原生 Anthropic / Gemini 协议。

推荐每个所有者一个实例，SQLite 和工人配置放在同一个持久卷。无需 Qdrant；SQLite FTS 可独立使用。已有部署如需复用数据库，先备份并在副本上检查升级，不能直接覆盖运行中的数据库。

## 本机

运行 `./scripts/start.sh`。脚本读取 `.env`（如果存在），再生成缺失的 Token、构建前端并启动。可设置 `MEMORY_STATE_DIR`、`MEMORY_HOST`、`MEMORY_PORT`。关闭终端会停止服务；长期运行应交给 systemd、launchd 或 Docker。

开发时先运行后端，再执行 `npm run dev --prefix frontend`；Vite 将 `/api` 代理到 `http://127.0.0.1:18200`。生产由 Python 直接提供构建产物。

## Docker

运行 `python3 scripts/init.py --compose` 创建本机 `data/access-token` 和 `.env`。已有文件不会被覆盖；若已有 `.env`，确认其中 `MEMORY_TOKEN` 非空且至少 24 字符。随后 `docker compose up -d --build`。

- Compose 默认仅开放 `127.0.0.1:18200`。
- 容器以 uid/gid `10001` 运行；命名卷由 Docker 初始化权限。
- 使用自定义 bind mount 时先让 uid `10001` 能读写该目录。
- Docker 内访问宿主机模型服务不能填写 `127.0.0.1`；它指向容器自身。使用可从容器解析和访问的服务地址。
- 模型配置保存在 `/data/workers.json`，服务逐次读取，保存后无需重启。未完成请求继续使用原配置。
- 向量模型或端点变化后，旧向量不会与新向量混用，调度器会重新生成对应索引。
- 清除 Key 仅清除对应角色的认证值；可填新 Key 后保存。接口未要求认证时允许留空。

## HTTPS 与远程访问

保持应用监听本机，在 Caddy / Nginx 后发布。单独的域名根路径最简单；本版本不支持部署到 `/memory/` 等子路径。

Caddy 示例（将域名替换为自己的，并先完成 DNS）：

```caddyfile
memory.example.com {
    reverse_proxy 127.0.0.1:18200
}
```

反向代理保留原始 Host。公网部署将 `.env` 中 `XINHUO_SECURE_COOKIE=1`，重新创建容器或重启本机服务。浏览器只在 HTTPS 下发送 Secure Cookie。Token 和模型密钥应通过 HTTPS 输入。

登录会话 12 小时过期；退出登录立即撤销；服务重启也会使已有网页会话失效。登录失败有本进程内限速。应用不接受 URL 查询中的 Token。无需 CORS 放行。

## 主模型接入顺序

1. 主模型开始处理前，使用 `/events` 追加实际收到的原始事件；携带稳定 `source_msg_id` 以便重试去重。
2. 通过 `/recall` 召回，`mode=auto` 可携带会话键。只有实际注入/送达后调用 `/recall/commit`；取消的请求不得提交回执。
3. 主模型情绪出现显著变化时提交 `/affect/self-report`，引用刚刚入库的精确原文，提供 `turn_id` 或 `source_msg_id`。不要由网页用户代填为模型自述。
4. 主动唤醒调度器读取 `/affect/wake-policy`，执行 `skip_proactive` 硬限制；本服务不自带外呼或消息发送。

`AFFECT_INTAKE_MODE=self_report` 是完整部署入口默认值。`worker`、`dual` 用于兼容或比较；旧 `server.py` 单独入口仍沿用环境默认策略。

## 备份、升级与回退

首次部署不含任何生产数据。已有实例升级前，停止工人和 HTTP 写入后备份整个**该实例的数据目录**，保留原镜像/源码版本。SQLite 运行中备份要使用 SQLite Backup API，不能只复制主 `.sqlite3` 文件而漏掉 WAL。

`workers.json` 每次修改前自动备份到 `config-backups/`；这些备份同样包含旧密钥，必须限制访问。实例数据卷不应发布为静态目录。

更新代码并重新构建会进行兼容的添加式迁移；不会替换原始内容。回退代码应保留后续产生的数据；不要用旧整库覆盖新事件。`docker compose down` 保留卷，`down -v` 删除卷。

重启期间执行中的持久任务可通过过期租约继续处理。先等待任务完成再维护，避免正在执行的模型请求重复产生费用。

## 常见情况

- 登录失败：检查 `.env` 或 `data/access-token`，不是模型 API Key；检查是否开启了 Secure Cookie 却使用 HTTP。
- 保存成功但没有记忆：查看整理和复核两项配置、点击测试、检查队列；没有足够证据的闲聊不会被强制变成记忆。
- 无情绪/状态：没有主模型自述就显示缺失；只保存历史不会产生新的“此刻”。
- 召回降级：嵌入/重排序失败仍可走全文候选；复核失败返回空，不用未经审核的候选冒充已选记忆。
- 手机浏览：使用部署后的 HTTPS 域名；`127.0.0.1` 指向手机本身。
