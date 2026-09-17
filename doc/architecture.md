# 当前架构

## 关键目录与职责

```text
src/agent/
├─ event.py         Trace、Turn、Tool 生命周期事件
├─ tool.py          Tool 定义和 JSON Schema 参数校验
├─ trace.py         Trace、Turn 与 ToolExecution 状态
└─ loop.py          多 Turn 模型调用、工具执行和终止控制

src/model/
├─ contract.py      ChatModel 契约
├─ settings.py      OpenAI-compatible 配置
├─ openai_chat.py   真实流式模型实现
└─ fake.py          确定性测试模型

src/manage/         待构建

web/src/
├─ App.tsx          居中输入页、左右对话流、过程与 Markdown 回答
├─ chatStream.ts    真实 SSE 客户端
├─ types.ts         与后端事件对应的通用前端状态
└─ styles.css       响应式视觉样式
```

## 依赖方向

```text
React 前端
    ↓ SSE
FastAPI API
    ↓ 创建一次运行
ManageAgent
    ↓
AgentLoop → ChatModel
    ↓ 自主 Tool calls
自动发现的 tools ......
```

`AgentLoop` 只认识模型、消息和 `Tool` 协议。`ManageAgent` 每次创建新的 `ManageAgentRun`、`AgentTrace` 和 `ToolContext`，不检查某个业务工具是否“必经”。模型通过 Tool 描述自行选择调用；Tool 结果作为 tool message 回到同一 Trace 的后续 Turn。

## 运行与事件流

一次 HTTP 请求对应一个 Trace：

```text
trace_start
  → turn_start
  → 模型流式输出 / tool_start → tool_end
  → turn_end
  → 后续 turn（数量由模型行为决定）
  → trace_end
```

API 将内部事件投影为 `trace`、`turn`、`tool`、`delta`、`done` 和 `error`。`tool` 事件携带所属 Turn、输入参数和解析后的结果，`delta` 携带所属 Turn。前端在内部按 Turn 归属组织内容，但页面不显示该技术概念；公开说明保持可见，Tool 详情默认折叠，正常结束时将最后一段文本确认为 Markdown 正文且不重复展示。取消请求会停止消费本次事件流，不影响其他请求。
