# 记忆观察室前端

生产入口使用真实同源 `/api/*`，不读取 mock。完整运行方法见仓库根 README 与 `docs/deployment.md`。

```bash
npm ci
npm run build
```

由 `python3 xinhuo/room_runtime.py` 提供构建结果。开发服务 `npm run dev` 将 API 代理到本机 18200 端口，后端需另外运行。源码所有数据访问集中在 `src/api.ts`；组件不会直接接触服务端密钥。

Token 只用于创建 HttpOnly 会话；工人 API Key 提交后由服务器保存，配置 GET 仅返回 `hasApiKey`。浏览器本地只保存主题偏好。先前 mock 的本地 Key 不会自动迁移或上传；如曾用过旧演示版，可自行清理该站点旧存储。

生产数据分页载入，每批 100 条。全库查找有独立搜索与分页；时间线的小搜索框只筛选已载入条目。历史自述、每日印象与召回记录显示最近 100 条，完整数据仍可经 MCP / 数据库备份获取。候选审核先显示 100 条，处理后重新读取即可查看后续候选。

`src/mocks/` 为旧设计 fixture，仅供参考，产品构建不会引用。不能把 HTML 单文件导出当作可独立运行的记忆服务。
