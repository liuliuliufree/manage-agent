# 当前架构

## 关键目录与职责

```text
src/domain/
├─ goal.py          版本化经营目标、缺失信息与假设
├─ evidence.py      带来源、版本与有效期的最小证据
├─ opportunity.py   关联 Goal/Evidence 的经营机会判断
├─ capability.py    稳定 Capability 请求、结果与状态契约
├─ plan.py          Capability Plan 与轻量步骤依赖校验
└─ refs.py          Goal/Plan 的版本化引用

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

src/application/
├─ capability_catalog.py  M2-Lite Planner 可见的五类独立经营能力目录
├─ goal_parser.py         自然语言 Goal 解释、可信上下文合并与 Goal 构造
├─ planner.py             Goal + Existing Context + Catalog 到 M1 Plan
├─ plan_validation.py     Plan 与 Catalog 的四项轻量确定性校验
└─ business_agent.py      串联解析、澄清、规划和校验的轻量应用入口
```

## 依赖方向

```text
Application（M2-Lite）
       ├──→ Domain
       └──→ Model

未来能力执行：Application ──→ Agent Runtime ──→ Model
```

`domain` 不导入 `agent` 或 `model`；`agent` 与 `model` 也不导入 `domain`。Application 是唯一可同时组合领域契约、模型和通用 Runtime 的位置；当前 Goal Parser 与 Planner 直接依赖 `ChatModel`，BusinessAgent 只编排这两个应用组件，尚未组合 Agent Runtime。

Capability Catalog 是无固定流程语义的能力集合，不包含步骤编号、顺序或前后继关系。后续 Planner 应根据 Goal 与已有 Context 从中选择最少合理能力，而不能机械生成五步流程。

## 领域数据流

```text
原始经营请求 + 可信上下文
              ↓
 BusinessAgent → Goal Parser（模型解释语义，代码注入可信字段）
              ↓
 Goal（版本化）或 CLARIFICATION_REQUIRED
              ↓
 Planner（Goal + Existing Context + Catalog）
              ↓
 Plan Validation → PLAN_READY / FAILED
              ↓
CapabilityRequest / CapabilityResult
              ↓
Opportunity ← Evidence
```

M1 描述领域对象及其机器可校验不变量；M2-Lite 已通过 BusinessAgent 实现自然语言到 Goal、澄清或动态 Plan 的完整应用链路，但仍没有 Capability Runtime、业务 Tool、数据持久化或 HTTP API。CapabilityResult 的 `execution_meta.trace_id` 是字符串引用，避免 Domain 依赖 Agent Trace 类型；`rule_result_refs` 统一保存 `RULE_RESULT` Evidence ID，并由后续 Application 在可取得 Evidence 集合时解析类型。

Goal Parser 不把 `RuntimeContext` 发送给模型。模型只返回业务语义 JSON；Application 生成新 Goal ID、管理版本和原始请求，并以 RuntimeContext 覆盖可信 actor/channel。时间只接受用户原文表达，模型提供的起止日期不进入 Goal；产品和需求提及需在用户原文中出现。

Planner 将 Goal、简单引用 Context 和 Capability Catalog 发送给模型。模型只返回 `step_id`、`capability_id` 与 `depends_on`；Application 负责 Plan 身份和状态。Catalog 不携带固定顺序，已有机会、客户或任务上下文可以直接选择后续能力。

Planner 返回前调用独立 `validate_plan()`，确定性检查 capability_id 属于 Catalog、step_id 唯一、依赖目标存在且依赖图无环。该函数不判断业务语义是否合理，也不承担上下文依赖、版本绑定、输出类型或副作用治理。

BusinessAgent 是无持久状态的轻量 Orchestrator：Parser 要求澄清时不调用 Planner；正常时向 Planner 传递 Goal、Existing Context 和 Catalog，并再次守卫 Plan 合法性；解析、规划或校验异常统一收敛为带简单错误信息的 `FAILED` 响应。

## M1 已强制的契约

- Goal、Plan 版本不低于 1，`revise()` 创建新版本而不修改旧实例。
- Evidence 必须带非空 Source；EvidenceType 不包含 Agent judgement。
- 正式 Opportunity 必须指向具体 Goal version 且至少保留一条 EvidenceLink；优先级需要解释因素。
- Capability 状态语义区分无结果、业务规则阻断和运行失败；BLOCKED 要求规则结果引用。
- PlanStep 只选择 Capability，可重复、可省略；依赖必须存在且不能成环。

产品、客户、规则与 Trace 的事实来源，以及 Opportunity/Capability 语义是否被错误设计为固定 Demo 工作流，仍由后续实现与架构评审保证。
