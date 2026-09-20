
# M2-Lite 智慧经营超级 Agent 开发说明书

> 状态：已完成（2026-09-20）。Step 1～6 已实现并通过核心 Demo 行为测试；后续扩展按本文边界停止，待 Demo 验证与代码 Review 后再决定下一阶段。

## 1. 阶段目标

M2-Lite 只需要证明一件事：

**用户输入自然语言经营诉求后，系统能够理解用户的 Goal，并基于当前已有上下文，从可用 Capability 中动态选择合适能力形成 Plan。**

核心链路：

```text
User Request
    ↓
Goal Parser
    ↓
Goal
    ↓
Planner ← Capability Catalog
    ↓
Plan
```

外层由一个轻量 BusinessAgent 负责串联。

M2-Lite 不追求生产级治理，不实现复杂版本管理、完整审计、Capability 执行或 Replan。

---

# 2. 当前已有基础

M0 已完成通用 Runtime：

```text
src/agent/
├─ event.py
├─ tool.py
├─ trace.py
└─ loop.py

src/model/
├─ contract.py
├─ settings.py
├─ openai_chat.py
└─ fake.py
```

M1 已建立核心 Domain Contract，包括：

```text
Goal
Evidence
Opportunity
Capability
CapabilityResult
Plan
PlanStep
```

M2-Lite 应优先复用 M1 已有对象。

不要重新创建第二套：

```text
LiteGoal
LitePlan
DemoGoal
DemoPlan
```

如 M1 Contract 某些字段对于 Demo 非必需，可以为空或使用最小值，不要因此重构整个 M1。

---

# 3. M2-Lite 总体架构

建议新增轻量 Application 层：

```text
src/application/
├─ goal_parser.py
├─ capability_catalog.py
├─ planner.py
└─ business_agent.py
```

具体目录和文件名可根据当前项目代码风格调整。

整体关系：

```text
                    ┌──────────────────────┐
                    │ Capability Catalog   │
                    │ 当前有哪些能力       │
                    └──────────┬───────────┘
                               │
                               ▼
User Request → Goal Parser → Goal → Planner → Plan
     │                                      │
     └──────────── BusinessAgent ───────────┘
```

M2-Lite 不新增：

```text
GoalAssembler
ClarificationGate
PlanDraft
PlanValidator
PlanningEngine
CapabilityEngine
WorkflowEngine
```

除非现有代码已经存在类似机制且直接复用明显更简单。

---

# 4. Goal Parser

## 4.1 职责

Goal Parser 负责：

```text
Natural Language
      ↓
     Goal
```

即理解：

> 用户当前想完成什么经营目标？

Goal Parser 可以直接调用现有 ChatModel。

第一版不需要通过 AgentLoop。

---

## 4.2 Goal Parser 可以理解的内容

至少支持：

```text
goal_type
metric
target
time_horizon
audience_scope
product_or_need_context
constraints
```

如果用户没有表达某字段：

```text
保持为空
```

不要为了填满 Goal 而猜测。

---

## 4.3 必须保留的两条硬边界

### 边界一：可信身份信息不能由 LLM 决定

例如：

```text
actor
channel
authorization
```

如当前调用上下文中存在，应由代码覆盖/补充进入 Goal。

LLM 不得自己猜：

```text
当前用户是个险代理人
```

---

### 边界二：未知业务事实不能脑补

例如用户说：

```text
“开门红阶段”
```

可以：

```text
raw_expression = "开门红阶段"
```

不允许模型自己生成活动开始/结束日期。

例如：

```text
“50岁客户”
```

不允许自动生成：

```text
need = 养老需求
```

因为这已经属于后续经营判断。

---

# 5. Goal Parser 的输入

第一版可以非常简单：

```text
user_request
runtime_context
existing_goal optional
```

其中 Runtime Context 最少包含：

```text
actor_ref
channel_ref
```

如果当前 Demo 没有真实登录用户上下文，可以使用测试配置中的固定可信值。

但固定值必须来自 Application 配置，而不是 LLM Prompt。

---

# 6. Goal 修改

M2-Lite 不需要建设复杂 Goal Patch Framework。

但需要支持一个 Demo 常见场景：

已有：

```text
Goal v1
目标 = 500W NBEV
产品 = A、B
```

用户：

```text
“改成400W”
```

结果应保留：

```text
metric = NBEV
products = A、B
```

只修改：

```text
target = 400W
```

可以直接通过：

```text
existing_goal
+
LLM理解用户修改
```

完成。

如果实现复杂度明显增加，可以先支持最基本 SET 修改。

CLEAR 语义，例如：

```text
“不限定产品了”
```

如果容易实现则支持；

如果当前 Demo 暂时没有此交互需求，可以延后，不要为了 CLEAR 单独设计复杂 FieldUpdate 系统。

---

# 7. Clarification 简化策略

M2-Lite 不建立独立 ClarificationGate。

Goal Parser 可以直接返回：

```text
GoalParseResult
```

概念上：

```text
goal
need_clarification
clarification_question
```

例如：

用户：

```text
“这个月业绩做到500W”
```

因为：

```text
“业绩”
```

不能明确判断是 NBEV、保费还是其他指标。

则直接：

```text
need_clarification = true
question = “这里的500W具体指NBEV、保费还是其他指标？”
```

此时 BusinessAgent 不进入 Planner。

即可。

不要实现：

```text
UnresolvedItem
ClarificationDecision
ClarificationResult
required_before_planning
required_before_execution
```

整套机制。

---

# 8. Capability Catalog

Capability Catalog 是 M2-Lite 必须保留的核心。

原因：

> 它是证明系统不是固定五步 Workflow 的关键。

第一版可以非常简单。

例如：

```python
CAPABILITIES = {
    "directional_insight": {
        "description": "识别与当前经营目标相关的经营机会和问题"
    },
    "customer_targeting": {
        "description": "围绕明确经营机会寻找候选经营客户"
    },
    "strategy_generation": {
        "description": "针对明确客户或对象形成下一步经营策略"
    },
    "validation_distribution": {
        "description": "对经营对象和动作进行必要校验，并支持后续合法分发"
    },
    "tracking_iteration": {
        "description": "查看经营任务进展、触达反馈和目标进展"
    }
}
```

可以复用 M1 的 CapabilityDefinition。

不要求第一版实现：

```text
required_context
required_any
optional_context
produces
side_effect_level
capability_version resolving
availability registry
```

除非现有 M1 已经实现并且直接使用非常简单。

---

# 9. Capability Catalog 的核心约束

Catalog 绝对不能包含：

```text
order
step_number
previous_capability
next_capability
```

也不能写成：

```text
1. 定向洞察
2. 自动圈客
3. 策略生成
4. 校验分发
5. 追踪迭代
```

它们是五类能力，不是五个固定步骤。

Planner 应该看到的是一个无序能力集合。

---

# 10. Planner

## 10.1 职责

Planner 负责：

```text
Goal
+
已有 Context
+
Capability Catalog
       ↓
      Plan
```

Planner 可以直接调用 ChatModel。

M2-Lite 不需要 AgentLoop。

---

# 11. Planner Prompt 核心原则

必须明确告诉 Planner：

```text
根据当前 Goal 和已有 Context，
从 Capability Catalog 中选择完成当前请求所需的最少合理能力。

Capability 没有固定执行顺序，
可以跳过、重复和重新排列。

如果已有 Context 已经满足某个后续能力的需要，
不要重复执行无意义的前置能力。

不得创造 Catalog 中不存在的 Capability。
```

不要告诉模型：

```text
智慧经营需要依次经过五个阶段……
```

即使后面再写：

```text
可以灵活调整
```

也不要。

---

# 12. Planner 输入

第一版输入可以控制为：

```text
Goal
Existing Context Summary
Capability Catalog
```

Existing Context 不需要建立复杂 PlanningContext Contract。

Demo 可以直接使用一个简单结构：

```python
context = {
    "opportunity_refs": [],
    "customer_refs": [],
    "strategy_refs": [],
    "task_refs": [],
}
```

甚至如果当前 Demo 第一版没有历史上下文，可以先为空。

重点是保留未来扩展位置。

---

# 13. Planner 输出

直接输出 M1 的：

```text
Plan
PlanStep
```

不再设计：

```text
PlanDraft
→ PlanValidator
→ Plan
```

双层模型。

Planner 可以输出：

```text
step_id
capability_id
objective
reason
depends_on
```

如果 M1 PlanStep 需要更多字段，使用最小合法值即可。

---

# 14. Plan 轻量校验

M2-Lite 仍然需要一个非常小的确定性校验函数。

例如：

```python
validate_plan(plan, capability_catalog)
```

只检查：

1. capability_id 必须存在于 Catalog。
2. step_id 不重复。
3. depends_on 必须指向存在的 Step。
4. 不允许 dependency cycle。

就够了。

不要为 Demo 实现：

```text
Context Dependency Solver
Capability Version Binding
Output Type Validation
Side Effect Validator
Semantic Repair
```

---

# 15. Planner 失败处理

如果模型：

```text
返回非法 JSON
```

允许一次格式修复。

如果仍失败：

```text
直接返回 planning failure
```

如果生成不存在的 Capability：

```text
validate_plan() 失败
```

Demo 第一版可以直接失败并记录日志。

不需要：

```text
Planner semantic repair
→ 再规划
→ 再 Validator
```

这属于 Pilot 阶段。

---

# 16. BusinessAgent

BusinessAgent 是整个 M2-Lite 的统一入口。

它不是 AgentLoop。

它只是轻量 Application Orchestrator。

概念代码：

```python
class BusinessAgent:

    def handle(
        self,
        user_request,
        runtime_context=None,
        existing_goal=None,
        existing_context=None,
    ):

        parse_result = self.goal_parser.parse(
            user_request=user_request,
            runtime_context=runtime_context,
            existing_goal=existing_goal,
        )

        if parse_result.need_clarification:
            return clarification_response(...)

        goal = parse_result.goal

        plan = self.planner.plan(
            goal=goal,
            context=existing_context,
            capabilities=self.capability_catalog,
        )

        validate_plan(
            plan,
            self.capability_catalog,
        )

        return {
            "goal": goal,
            "plan": plan,
        }
```

不要把 BusinessAgent 实现成：

```text
新的 Agent Loop
新的 Workflow Engine
新的状态机
```

---

# 17. M2-Lite Response

第一版只需要三种结果：

```text
PLAN_READY
CLARIFICATION_REQUIRED
FAILED
```

`PLAN_READY`：

```text
goal
plan
```

`CLARIFICATION_REQUIRED`：

```text
goal optional
question
```

`FAILED`：

```text
简单错误信息
```

暂时不需要复杂：

```text
ApplicationFailureStage
ApplicationFailure
NO_FEASIBLE_PLAN
PlanValidationError hierarchy
```

如果 Planner 判断当前系统无法完成，也可以直接返回：

```text
FAILED / unsupported
```

或者增加一个简单：

```text
UNSUPPORTED
```

但不要为此构建复杂错误体系。

---

# 18. M2-Lite 必须验证的 Demo 场景

第一版建议只保留 6～8 个核心场景。

## Case 1：只看经营机会

用户：

```text
“最近有什么值得关注的经营机会？”
```

合理 Plan：

```text
directional_insight
```

禁止机械生成五步。

---

## Case 2：已有 Opportunity 找客户

已有：

```text
opportunity
```

用户：

```text
“围绕刚才这个机会找一批客户。”
```

合理：

```text
customer_targeting
```

不应该重新：

```text
directional_insight
```

---

## Case 3：已有 Customer 求策略

已有具体 Customer。

用户：

```text
“王女士下一步怎么经营？”
```

合理：

```text
strategy_generation
```

不应该重新圈客。

---

## Case 4：查看经营进展

用户：

```text
“看看上周经营任务进展怎么样。”
```

合理：

```text
tracking_iteration
```

---

## Case 5：复杂绩效 Goal

用户：

```text
“开门红阶段完成500W NBEV，主推产品A和产品B。”
```

Planner 可以组合多个 Capability。

例如可能：

```text
directional_insight
→ customer_targeting
→ strategy_generation
```

但测试不要要求必须精确等于这个 Plan。

只需要确认：

* Plan 与 Goal 有关；
* 没有明显无关步骤；
* 没有机械五步全部加入。

---

## Case 6：关键指标不明确

用户：

```text
“这个月业绩做到500W。”
```

应：

```text
CLARIFICATION_REQUIRED
```

Planner 不调用。

---

## Case 7：非 Demo 产品

用户：

```text
“最近主推Product X，帮我看看有什么经营机会。”
```

Domain / Planner 不需要代码修改。

---

## Case 8：非开门红场景

用户：

```text
“最近一个月想重点提升老客户二次经营。”
```

系统仍然能够：

```text
Goal
→ Dynamic Plan
```

证明架构没有绑定开门红 Demo。

---

# 19. 测试要求

M2-Lite 测试保持轻量。

## 必须自动化的测试

### Goal Parser

* 明确 NBEV + Target 可以解析。
* 模糊“业绩”触发 Clarification。
* 不生成不存在的活动日期。
* Runtime actor/channel 覆盖模型猜测。
* 50岁客户不得自动生成养老需求。

### Planner

* 只看机会 → Insight。
* 已有 Opportunity → Targeting，不重复 Insight。
* 已有 Customer → Strategy。
* Tracking 请求 → Tracking。
* Planner 不得使用 Catalog 外 Capability。

### Plan Validation

* Unknown Capability fail。
* Duplicate step_id fail。
* Unknown dependency fail。
* Dependency cycle fail。

### BusinessAgent

* Clarification 时 Planner call count = 0。
* 正常请求返回 Goal + Plan。

---

# 20. Behaviour Eval

Demo 阶段不要建设复杂 Eval Framework。

可以维护一个简单 Case 文件或测试参数表。

每个场景只记录：

```text
input
existing_context
must_include
must_not_include
max_steps(optional)
```

例如：

```text
Case:
已有 Opportunity 找客户

must_include:
customer_targeting

must_not_include:
directional_insight
```

第一版不需要：

```text
JudgeAgent
LLM-as-a-Judge
复杂评分系统
15种 Failure Label
```

---

# 21. M2-Lite 明确不做

本阶段不要实现：

```text
GoalInterpretation 独立层
GoalAssembler 独立组件
ClarificationGate 独立组件
FieldUpdate SET/CLEAR Framework
MissingInformation 双 Gate
Capability Version Binding
ContextRequirement DSL
PlanningContext 完整 Contract
PlanDraft
完整 PlanValidator
Planner Semantic Repair
Bounded Semantic Repair
ApplicationFailure 完整体系
SideEffectLevel
SideEffectIntent
Write ControlPoint 自动治理
NO_FEASIBLE_PLAN 完整状态
GoalRepository
PlanRepository
数据库
Capability 执行
CapabilityResult 驱动 Replan
真实定向洞察
真实圈客
真实策略生成
真实规则校验
任务创建
任务分发
Tracking 后端
Workflow Engine
LangGraph
多 Agent
```

这些都等实际 Demo 跑通、出现真实需要后再增加。

---

# 22. 仍然必须坚持的架构底线

虽然是 Lite 版本，以下原则不能为了快而破坏。

## 1. Goal 与 Plan 分离

Goal：

```text
用户想完成什么
```

Plan：

```text
系统准备怎么做
```

不要重新合并成一个巨大 LLM JSON。

---

## 2. Capability 不等于固定步骤

五类 Capability 可以：

```text
跳过
重复
重排
```

不能硬编码：

```text
1 → 2 → 3 → 4 → 5
```

---

## 3. Planner 只能选择真实 Capability

不能让模型自由发明能力名称。

---

## 4. 业务事实和经营判断保持分离

M2 可以暂时不全面使用 Evidence，但不要把：

```text
模型猜测
```

包装成：

```text
确定客户事实
```

---

## 5. Demo 值不能进入架构

以下内容只能是输入数据：

```text
开门红
御享分红26
御享金越年金
500W NBEV
王女士
```

不能成为：

```text
class
enum
固定 workflow
硬编码 planner 分支
```

---

# 23. 推荐开发顺序

请按以下顺序开发：

```text
Step 1
Capability Catalog
```

先定义 Planner 能看到哪些能力。

```text
Step 2
Goal Parser
```

完成 Natural Language → Goal。

```text
Step 3
Planner
```

完成 Goal + Context + Catalog → Plan。

```text
Step 4
Lightweight Plan Validation
```

只做基础合法性检查。

```text
Step 5
BusinessAgent
```

串起完整链路。

```text
Step 6
6~8个核心 Demo Test / Behaviour Eval
```

不要提前扩范围。

---

# 24. 推荐实现风格

优先：

```text
简单函数
小类
dataclass
明确输入输出
FakeModel
依赖注入
少量 Prompt
少量 DTO
```

避免：

```text
Manager
Factory
Engine
Registry of Registries
复杂继承
大状态机
大量抽象接口
```

除非当前项目已有成熟模式。

---

# 25. Codex 开发过程要求

开始开发前：

1. 阅读 AGENTS.md。
2. 阅读当前 M0/M1 真实代码。
3. 阅读 current-state.md / architecture.md / dev-log.md。
4. 确认 Python 版本和测试框架。
5. 优先复用已有 Domain Contract。
6. 不因为本说明书示例与实际代码字段不同就重构整个 M1。

如果发现某项 M1 Contract 对 M2-Lite 使用不方便：

优先采用最小适配。

不要自行做大规模架构重构。

---

# 26. 完成后需要报告

Codex 最终请提供：

1. 新增/修改文件。
2. 最终 Application 目录结构。
3. Goal Parser 输入输出。
4. Capability Catalog 内容。
5. Planner Prompt 核心规则。
6. Plan Validation 实现范围。
7. BusinessAgent 完整调用链。
8. 自动测试结果。
9. 核心 Demo 场景结果。
10. 哪些原 M2 完整设计被有意延后。
11. 是否出现任何 Demo 硬编码。
12. 实际执行的测试命令。

---

# 27. M2-Lite Definition of Done

满足以下条件即可结束 M2-Lite：

```text
Natural Language
→ Goal
正常工作
```

```text
Goal
+
Existing Context
+
Capability Catalog
→ Dynamic Plan
正常工作
```

并且：

* 只看 Opportunity 时不会生成固定五步。
* 已有 Opportunity 时可以直接 Targeting。
* 已有 Customer 时可以直接 Strategy。
* Tracking 请求可以直接 Tracking。
* 关键 Goal 模糊时会 Clarification。
* Planner 不能发明 Catalog 外 Capability。
* Plan 基础 dependency 合法。
* Product X、非开门红场景无需修改代码。
* 所有核心 Demo Tests 通过。

满足以上条件：

```text
M2-Lite = DONE
```

随后停止继续扩展 M2。

先进行 Demo 验证和代码 Review，再决定进入：

```text
M3-Lite：
Plan → Capability 执行 → Result → 简单动态继续
```

还是补齐部分完整 M2 能力。
