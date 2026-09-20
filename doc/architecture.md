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
├─ capability_executor.py M3-T01 按 capability_id 分发 callable handler，并将调用故障收敛为 CapabilityResult
├─ continuation.py        M3-T05 将最近 CapabilityResult 映射为下一运行行为
├─ execution_context.py   M3-T02 保存当前 Goal、Plan、已知事实与按 step_id 记录的 CapabilityResult
├─ step_execution.py      M3-T03 将 PlanStep 映射为 CapabilityRequest，执行并记录 CapabilityResult
├─ step_resolution.py     M3-T04 根据已有 CapabilityResult 解析首个 Ready Step
├─ goal_parser.py         自然语言 Goal 解释、可信上下文合并与 Goal 构造
├─ planner.py             首次规划及 NO_RESULT 后完整 Plan 新版本生成
├─ plan_validation.py     Plan 基础校验及成功旧步骤重规划身份校验
└─ business_agent.py      串联解析、澄清、规划、执行和一次重规划的轻量应用入口
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
 Plan Validation → ExecutionContext
              ↓
Ready Step → CapabilityRequest / CapabilityResult
              ↓
Continue / Replan once / Complete / Ask User / Stop
              ↓
Opportunity ← Evidence
```

M1 描述领域对象及其机器可校验不变量；M2-Lite 与 M3-Lite 已通过 BusinessAgent 实现自然语言到 Goal、动态 Plan、Capability handler 执行和一次结果驱动重规划的应用闭环，但仍没有真实业务 Capability、数据持久化或 HTTP API。CapabilityResult 的 `execution_meta.trace_id` 是字符串引用，避免 Domain 依赖 Agent Trace 类型；`rule_result_refs` 统一保存 `RULE_RESULT` Evidence ID，并由后续 Application 在可取得 Evidence 集合时解析类型。

Goal Parser 不把 `RuntimeContext` 发送给模型。模型只返回业务语义 JSON；Application 生成新 Goal ID、管理版本和原始请求，并以 RuntimeContext 覆盖可信 actor/channel。时间只接受用户原文表达，模型提供的起止日期不进入 Goal；产品和需求提及需在用户原文中出现。

Planner 将 Goal、简单引用 Context 和 Capability Catalog 发送给模型。模型只返回 `step_id`、`capability_id` 与 `depends_on`；Application 负责 Plan 身份和状态。Catalog 不携带固定顺序，已有机会、客户或任务上下文可以直接选择后续能力。

同一个 `Planner` 通过 `replan()` 处理 M3-T06 的单一恢复场景：最近一次 Capability 正常执行但返回 `NO_RESULT`。输入增加当前完整 Plan、`known_context`、按 step_id 保存的历史结果和最近结果；模型仍只返回完整步骤集合。Application 使用既有 `Plan.revise()` 保持 plan_id、递增版本并记录 `supersedes_version`，不新增 Replan ID、PlanPatch 或第二套规划框架。

Planner 返回前调用独立 `validate_plan()`，确定性检查 capability_id 属于 Catalog、step_id 唯一、依赖目标存在且依赖图无环。重规划随后调用 `validate_replan()`，只防止已取得 `SUCCESS/PARTIAL_SUCCESS` 的旧 step_id 在新 Plan 中被复用为不同 capability；失败旧步骤留在 `ExecutionContext.step_results` 作为历史事实，Replan Prompt 要求不把它保留在新的依赖链中。校验不判断业务语义是否合理，也不承担上下文依赖、版本绑定、输出类型或副作用治理。

BusinessAgent 是无持久状态的轻量 Orchestrator：Parser 要求澄清时不调用 Planner；正常时向 Planner 传递 Goal、Existing Context 和 Catalog，校验 Plan 后创建 ExecutionContext，并直接组合 Ready Step、单步执行和继续策略。成功步骤自动推进；`NO_RESULT` 最多触发一次 `Planner.replan()`；`NEED_INFORMATION` 返回澄清；`BLOCKED/FAILED` CapabilityResult 返回 `STOPPED`；解析、规划、重规划或校验异常收敛为带简单错误信息的应用级 `FAILED` 响应。响应保留最终 Plan、ExecutionContext 与最近 CapabilityResult，未新增 Engine 或第二套运行状态。

CapabilityExecutor 是 Application 层的最小执行分发器，与 Planner 使用的 Capability Catalog 分离。它接收已有 `CapabilityRequest`，按 `capability_id` 调用普通 callable handler，并原样返回 handler 的 `CapabilityResult`；未注册和调用异常分别收敛为依赖类与内部类 `FAILED` 结果。BusinessAgent 负责组合它与其他执行函数；Executor 自身不从 PlanStep 构造请求、记录结果、调度依赖或重规划。

ExecutionContext 是 Application 层最小可变运行状态，仅持有当前 `Goal`、当前 `Plan`、普通字典 `known_context` 和 `step_id -> CapabilityResult` 映射。`record_result()` 只保存或替换指定步骤的最新结果；已知事实与执行历史保持分离，输出解释、上下文合并和 Plan 历史均未实现。

`build_capability_request()` 是 M3-T03 的普通映射函数：从 PlanStep、ExecutionContext 中取 capability_id、当前 Goal/Plan 版本、可信 actor/channel 来源和已知上下文，构造 M1 既有的 CapabilityRequest。`execute_step()` 顺序调用该函数、CapabilityExecutor 和 `ExecutionContext.record_result()`；成功与失败结果都会记录。BusinessAgent 驱动该执行链路，但这两个函数本身不负责步骤就绪判断、依赖调度、输出合并或继续策略。

`is_step_ready()` 与 `get_next_ready_step()` 是 M3-T04 的两个无状态函数。前者把“未执行且所有依赖结果为 `SUCCESS` 或 `PARTIAL_SUCCESS`”定义为 Ready，后者按 Plan 中的出现顺序返回第一个 Ready Step；`NO_RESULT`、`FAILED`、`BLOCKED` 等结果不会释放后继依赖。当前不持久化第二套 Step Runtime Status，也不区分“Plan 已完成”和“Plan 已卡住”；这些属于后续继续策略，而不是 Ready Step 解析职责。

`is_plan_finished()` 与 `decide_continuation()` 是 M3-T05 的无状态继续策略。前者仅在 Plan 每个步骤都已有 `SUCCESS` 或 `PARTIAL_SUCCESS` 结果时返回完成；后者复用 Ready Step 解析，将成功类结果导向 `CONTINUE/FINISH`，将 `NO_RESULT` 导向 `REPLAN`，将缺信息导向 `ASK_USER`，将业务阻断、技术失败和无法继续的不一致状态导向 `STOP`。T07 已由 BusinessAgent 调用这些组件形成最小执行闭环；仍未实现重试、降级、自动补信息、多轮重规划或生产持久化。

## M1 已强制的契约

- Goal、Plan 版本不低于 1，`revise()` 创建新版本而不修改旧实例。
- Evidence 必须带非空 Source；EvidenceType 不包含 Agent judgement。
- 正式 Opportunity 必须指向具体 Goal version 且至少保留一条 EvidenceLink；优先级需要解释因素。
- Capability 状态语义区分无结果、业务规则阻断和运行失败；BLOCKED 要求规则结果引用。
- PlanStep 只选择 Capability，可重复、可省略；依赖必须存在且不能成环。

产品、客户、规则与 Trace 的事实来源，以及 Opportunity/Capability 语义是否被错误设计为固定 Demo 工作流，仍由后续实现与架构评审保证。
