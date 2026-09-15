# 当前架构

## 关键目录与职责

```text
src/agent/
├─ event.py         运行过程的结构化事件契约
├─ tool.py          工具定义、JSON Schema 编译与参数校验边界
├─ trace.py         Trace、Turn 与工具执行记录
└─ loop.py          全 Turn 流式模型调用、工具执行与循环控制

src/model/
├─ contract.py      ChatModel 结构化调用契约
├─ settings.py      模型连接配置加载与校验
├─ openai_chat.py   OpenAI-compatible Chat Completions 实现
├─ fake.py          确定性测试实现
└─ errors.py        稳定的模型调用错误边界

src/manage/
├─ repository.py    只读取场景 source 数据并校验快照、引用与规则版本
├─ contracts.py     经营任务、机会组合、圈客、客户证据和 Agent 结果契约
├─ service.py       三类机会、综合排序、硬规则、优先级和证据的确定性计算
├─ tools.py         四个业务 Tool 及单次 Agent 运行的正式产物收集
├─ prompts.py       稳定 System Prompt 与运行任务消息模板
├─ workflow.py      前三幕 Agent 用例、必经产物检查和确定性降级
└─ __main__.py      本地真实模型运行入口

scripts/
├─ smoke_model.py                 使用本地配置验证真实模型连接
├─ smoke_agent_loop.py            使用 FakeChatModel 离线验证工具调用闭环
└─ generate_demo_mock_data.py     生成并重算校验前三幕合成 CSV 场景

data/scenarios/demo_acts_1_3_v1/
├─ source/                   业务运行可读取的 12 份合成原始数据 CSV
└─ test_expectations/        仅供测试断言使用的期望结果 CSV

tests/
├─ test_demo_mock_data.py    校验场景业务不变量与逐字节可重复生成
├─ test_manage_service.py    校验正式业务计算、证据、规则和数据隔离
└─ test_manage_workflow.py   校验 Agent Tool 闭环与确定性降级

web/
├─ src/App.tsx               单对话工作区、三幕进度与输入交互
├─ src/chatStream.ts         SSE/NDJSON 流解析与内置演示流适配
├─ src/styles.css            响应式视觉系统与克制动效
└─ vite.config.ts            Vite 开发与 `/api` 代理配置
```

## 依赖方向

```text
Agent Core
      ↓ ChatModel
模型调用层
      ↓ OpenAI Python SDK
OpenAI-compatible 接口
```

前三幕业务依赖方向为：

```text
Agent 用例 → 业务 Tool → 确定性 ManageService → 场景 Repository → source CSV
     ↓
Agent Core → ChatModel → OpenAI-compatible 接口或 Fake 模型
```

Agent Core 不感知具体业务。业务 Tool 只调用 `ManageService`，主 Agent 不直接读取 CSV。`ManageService` 的汇总由客户明细派生，规则参数来自场景规则快照。生成器创建 source 与测试期望后，也通过正式 `ManageService` 重算并校验结果；正常业务路径不读取 `test_expectations/`。

`workflow.py` 收集 Tool 返回的正式产物并检查经营上下文、机会分析和客群筛选是否齐全，同时校验最终文本是否保持推荐机会、漏斗数字和合成数据标识。模型调用失败、漏掉必经 Tool、关键文本不一致或没有最终文本时，用例直接复用同一确定性服务形成产物和模板说明，并在结果中标记降级原因。

前端与后端通过独立的流适配层解耦。前端期望 `POST /api/chat/stream` 接收 `message` 与 `scenario_id`，并以 SSE 或逐行 JSON 返回 `act`、`delta`、`done`、`error` 事件。未配置 `VITE_API_BASE_URL` 时，适配层使用与当前场景事实一致的内置演示流；该演示流只用于页面开发，不是业务事实计算入口。
