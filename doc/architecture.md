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

src/manage/
├─ agent.py             通用经营 Agent 与单次 ManageAgentRun
├─ api.py               FastAPI SSE 边界和 Agent 事件映射
├─ data_repository.py   版本化业务数据快照读取和一致性校验
├─ contracts.py         确定性业务结果契约
├─ service.py           当前机会、规则、筛选和证据计算
├─ errors.py            稳定业务错误边界
├─ prompts/
│  └─ management.py             稳定角色约束与运行时消息模板
├─ tools/
│  ├─ __init__.py               自动扫描 Tool 模块并校验唯一名称
│  ├─ _context.py              单 Trace 的依赖、服务缓存和产物观察
│  ├─ _schema.py               共享参数 Schema 片段
│  ├─ business_context.py      经营目标、边界和规则查询 Tool
│  ├─ opportunity_analysis.py  机会识别、比较和排序 Tool
│  ├─ customer_segmentation.py 客户硬规则筛选和优先级 Tool
│  └─ customer_decision.py     单客户决策证据 Tool
└─ __main__.py          命令行入口

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
ManageAgent → prompts
    ↓
AgentLoop → ChatModel
    ↓ 自主 Tool calls
自动发现的 tools → ManageService → BusinessDataRepository → source CSV
```

`AgentLoop` 只认识模型、消息和 `Tool` 协议。`ManageAgent` 每次创建新的 `ManageAgentRun`、`AgentTrace` 和 `ToolContext`，不检查某个业务工具是否“必经”。模型通过 Tool 描述自行选择调用；Tool 结果作为 tool message 回到同一 Trace 的后续 Turn。

Tool 模块是当前业务扩展点。`src/manage/tools/__init__.py` 按稳定名称扫描所有非私有模块，并调用其 `create_tool(context)` 工厂。新增 Tool 不需要修改 Agent 或前端。Tool 可以调用本地确定性函数、外部服务或独立模型，只要遵守统一 Tool 协议。

确定性业务服务目前消费原前三幕合成数据，但它位于 Tool 内部，不定义 Agent 的流程。后续故事可以增加数据、Tool 或服务能力；前端只消费通用 `tool` 事件，因而不会依赖幕次数量或工具名称。

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
