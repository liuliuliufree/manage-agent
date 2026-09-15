# Manage Agent

前三幕经营分析后端与精简 React 对话前端。

## 启动前端

```powershell
Set-Location .\web
npm install
npm run dev
```

打开 `http://127.0.0.1:5173/`。未配置接口时，页面使用当前前三幕合成数据的内置演示流。

接入真实流式服务时，复制 `web/.env.example` 为 `web/.env.local`，设置 `VITE_API_BASE_URL`。前端默认向 `POST /api/chat/stream` 发送：

```json
{"message":"分析近期值得重点经营的加保机会","scenario_id":"demo-acts-1-3"}
```

响应可以是 SSE 的 `data: {...}`，也可以是逐行 JSON。支持的事件为 `act`、`delta`、`done` 和 `error`，具体字段见 `web/src/types.ts`。

## 构建前端

```powershell
Set-Location .\web
npm run build
```
