# Manage Agent

面向保险经营领域的通用智能体。当前仓库使用一份合成数据展示经营目标理解、机会分析和客户筛选，但“前三幕”只是当前演示内容，不是 Agent 的流程或代码边界。

## 运行后端

在项目根目录准备 `.env` 中的 OpenAI-compatible 模型配置，然后执行：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn manage.api:app --reload
```

后端提供 `POST /api/chat/stream`，请求体为：

```json
{
  "message": "分析近期值得重点经营的加保机会",
  "data_source_id": "demo-acts-1-3"
}
```

响应为 SSE，事件包括 `trace`、`turn`、`tool`、`delta`、`done` 和 `error`。`tool` 事件包含本次调用的 Turn、输入参数和返回结果；`delta` 携带所属 Turn。工具步骤来自 Agent 的实际调用，不对应固定幕次。

也可以直接运行命令行入口：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m manage "分析近期值得重点经营的加保机会"
```

## 运行前端

先启动后端，再打开另一个 PowerShell：

```powershell
Set-Location .\web
npm install
npm run dev
```

访问 `http://127.0.0.1:5173/`。Vite 默认把 `/api` 代理到 `http://127.0.0.1:8000`；独立部署时可通过 `web/.env.example` 配置接口地址、流路径和数据源标识，并由部署层处理同源代理或 CORS。

## 验证

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
Set-Location .\web
npm run build
```

新增模型工具时，在 `src/manage/tools/` 下增加一个非私有模块并导出 `create_tool(context)`；Agent 会自动发现，无需维护集中式工具清单。相关提示词统一位于 `src/manage/prompts/`。
