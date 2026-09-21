# M1 领域契约整体设计

> 状态：已确认并已实现
>
> 最近校准：2026-09-21
>
> 适用范围：`src/domain/` 的当前核心契约及其后续演进边界

## 1. 文档定位

本文是 M1 的唯一整体设计文档，合并并替代原 T01～T08 分篇。当前契约以已验证代码为事实源；本文负责解释为什么保留这些对象、它们之间如何关联，以及哪些细节必须等到出现真实消费者后再新增。

M1 的目标不是实现洞察、圈客、策略或任务分发，而是建立智慧经营 Agent 运行所依赖的最小稳定业务语言：

```text
Goal → Plan → PlanStep → CapabilityRequest → CapabilityResult
  └──────── Opportunity ← Evidence ────────┘
```

“未来有用途”不等于“现在必须进入核心 Contract”。字段进入核心契约前必须回答：

> 删除该字段后，当前 M2-Lite、近期 M3/M4 是否无法正确运行，或无法区分关键业务语义？

如果答案是否定的，字段应删除、延后，或放入真正消费它的阶段产物中。

## 2. M1 边界

### 2.1 依赖方向

```text
Application ──→ Domain
     │
     ├────────→ Agent Runtime ──→ Model
     └──────────────────────────→ Model
```

- `domain` 描述 Goal、Evidence、Opportunity、Capability 和 Plan，不依赖 Agent、Model、Prompt、Tool 或 Trace。
- `agent` 提供通用循环、Tool 调用和 Trace，不感知客户、产品、NBEV 或 Opportunity。
- `model` 只负责模型通信，不感知 Agent 和业务领域。
- `application` 是组合点，负责解析、规划、请求映射、执行协调和继续策略。

业务状态与运行状态分离：`goal_id`、`plan_id` 不等于 `trace_id`；Domain 只通过字符串引用关联 Trace，不复制 Turn、ToolExecution、消息或异常堆栈。

### 2.2 M1 不负责

- Goal Parser 或 Planner Prompt；
- 真正的洞察、圈客、策略、规则或任务创建实现；
- 数据库、Repository、恢复机制或生产审计平台；
- 固定五步工作流、分支 DSL、循环 DSL 或重试引擎；
- 多 Agent 拆分；
- 为 M5～M7 提前设计没有消费者的治理对象。

## 3. 核心关系

```text
Goal
  │  经营者想完成什么
  ▼
Plan(versioned)
  │  当前选择哪些 Capability，以及必要依赖
  ▼
PlanStep
  │
  ▼ Application 映射
CapabilityRequest
  │  本次调用的 Goal/Plan/主体/对象/输入引用
  ▼
CapabilityResult
  │  明确的业务状态、产物、证据、规则和错误
  ├──────────────┐
  ▼              ▼
Evidence      Opportunity
可信依据       基于证据形成的经营问题判断
```

Capability 是稳定业务语义，Tool 是可执行技术协议。一个 Capability 可以由本地函数、外部服务、规则、模型或多个 Tool 实现，但主 Agent 不感知具体实现方式。

## 4. Goal Contract

Goal 是不可变、可版本化的经营意图，只回答“要完成什么”，不回答“怎么完成”。

### 4.1 当前结构

| 字段 | 语义 |
| --- | --- |
| `goal_id / version` | 稳定身份和版本 |
| `original_request` | 用户原始表达，必填且不可丢失 |
| `goal_type` | 可扩展目标分类，不预先锁死枚举全集 |
| `metric / target` | 可选指标与目标值/方向 |
| `time_horizon` | 原始时间表达及有来源的起止日期 |
| `audience_scope` | 经营对象范围，不是查询 DSL |
| `product_or_need_context` | 用户明确表达的产品或需求背景 |
| `channel_and_actor` | 由可信运行上下文提供的渠道和人员 |
| `constraints` | 用户或上下文提出的目标约束，不等于业务规则 |
| `missing_information` | 已知缺失、影响和执行前是否必须补齐 |
| `assumptions` | 为继续工作采用的可修正假设 |

`Metric`、`Target`、`TimeHorizon`、`AudienceScope`、`ProductOrNeedContext`、`ChannelAndActor`、`Constraint`、`MissingInformation` 和 `Assumption` 只承载各自最小语义及结构校验。

### 4.2 不变量

1. `goal_id` 非空，`version >= 1`，原始请求和目标类型非空。
2. Goal 可以不完整；未知值保持 `None`，不得为结构完整而臆造事实。
3. 影响规划或执行的缺失通过 `missing_information` 显式表达。
4. 假设不得伪装成事实，必须进入 `assumptions`。
5. Goal 不包含 Capability、Tool、步骤顺序、Workflow 或经营结论。
6. Demo 阶段、目标值、产品和渠道只是值，不进入 Schema。
7. 修改目标产生同一 `goal_id` 的新版本，旧版本不可变。
8. 量化目标的完成条件由 `metric + target` 推导，不重复保存同义 `success_criteria`。

## 5. Evidence Contract

Evidence 是“可追溯依据的最小结构化表示”，不是业务数据仓库副本，也不是 Agent 结论。

### 5.1 类型边界

| 类型 | 含义 | 确定性 |
| --- | --- | --- |
| `CUSTOMER_FACT` | 客户事实 | 是，必须有权威来源 |
| `PRODUCT_FACT` | 产品事实 | 是，必须有适用版本 |
| `BUSINESS_FACT` | 经营阶段、任务、互动或业绩事实 | 是 |
| `RULE_RESULT` | 权威规则裁决 | 是，裁决优先于 Agent 建议 |
| `MODEL_SIGNAL` | 模型输出或评分信号 | 否 |
| `EXPERIENCE` | 经治理的经营经验 | 否，仅供参考 |

不存在 `AGENT_JUDGEMENT` 类型。Agent 判断应成为 Opportunity、Strategy 或 Decision，并引用 Evidence；不能生成结论后再把结论包装成证据证明自己。

### 5.2 当前结构

```text
Evidence
├── evidence_id
├── evidence_type
├── subject_ref?
├── field?
├── value?
├── summary
├── source
│   ├── source_id
│   ├── source_type
│   ├── version?
│   └── retrieved_at?
├── observed_at?
├── effective_period?
├── confidence?
└── limitations[]
```

- `field/value` 提供最小机器可读内容，`summary` 提供人可读解释。
- `source` 保存来源身份、类型、版本和取得时间；复杂源对象只保存引用，不复制完整客户画像、保单、模型输入或规则对象。
- `observed_at` 表示观察时间，`effective_period` 表示知识或规则适用期。
- `confidence` 主要用于 `MODEL_SIGNAL`，范围为 `[0, 1]`；确定性事实不要求伪造置信度。
- `limitations` 仅在确有适用限制时填写。

### 5.3 不变量

1. Evidence 必须有非空 ID、摘要和 Source。
2. 事实、规则、模型信号和经验必须保持类型边界。
3. 模型信号不能升级为客户事实，经验不能升级为规则。
4. Rule Result 不能被模型或 Agent 覆盖。
5. 证据与结论分离；“高潜客户”“存在养老机会”不是客户事实。
6. 来源冲突必须保留，不能由 Agent 静默择一。
7. Evidence 只保存当前判断所需最小内容，不提供开放式 `payload`。
8. 数据完整度属于数据获取结果或 CapabilityResult，不作为每条 Evidence 的统一质量字段。

## 6. Opportunity Contract

Opportunity 是针对具体 Goal 版本、基于 Evidence 形成的经营问题判断。它不是客户标签、产品推荐、规则结果或流程指令。

### 6.1 当前结构

```text
Opportunity
├── opportunity_id
├── goal_ref
├── opportunity_type
├── problem_statement
├── evidence_links[]
│   ├── evidence_id
│   └── role: SUPPORTS | LIMITS | CONTRADICTS
├── priority?
└── priority_reason?
```

- `goal_ref` 直接复用统一的 `GoalRef`，不再维护重复的 `GoalLink`。
- `problem_statement` 描述值得解决的经营问题，不直接写“适合购买某产品”。
- 支持、限制和反驳证据可以同时存在，不得为形成漂亮结论而删除反例。
- 优先级是可选的轻量表达；一旦提供 `priority`，必须同时提供 `priority_reason`。

### 6.2 不变量

1. Opportunity 必须关联明确 Goal 版本并至少引用一条 Evidence。
2. Opportunity 是判断，不是 Evidence 或确定性事实。
3. 类型不绑定开门红、某款产品或固定客户标签。
4. Opportunity 不携带 SQL、圈客 DSL 或权限裁决。
5. Opportunity 不通过 `next_action_hint` 控制 Planner；Planner 根据 Goal、已有 Context 和 Capability Catalog 决定下一步。
6. `goal_contributions`、`conditions`、`candidate_logic`、`validity` 等后续阶段信息不进入当前核心对象。

## 7. Capability Contract

### 7.1 CapabilityDefinition

当前定义只描述稳定能力身份：

```text
capability_id / name / description / version
```

能力 ID 不携带场景顺序，不等于“第一步、第二步”。五类能力可以被选择、跳过、重复或重排。

### 7.2 CapabilityRequest

CapabilityRequest 是统一调用信封：

```text
CapabilityRequest
├── request_id
├── capability_id
├── goal_ref
├── plan_ref?
├── actor_context
├── object_scope?
├── input_refs[]
└── as_of?
```

- `actor_context` 包含 actor、channel 和可信来源，不能由模型伪造。
- `object_scope` 表示本次调用实际处理的对象，与 Goal 的总体 audience scope 不同。
- `input_refs` 统一表达 `evidence:...`、`opportunity:...`、`customer:...`、`capability_result:...` 等已存在对象引用。
- `as_of` 表示本次判断的数据时间点。
- Application 当前只把 `known_context` 中命名为 `*_refs` 的字符串集合转换为 `input_refs`，不透传任意 `business_context`。

当前不保留 `CapabilityContext`、开放式 attributes、请求级万能 constraints 或 requested outputs。某项输入在具体能力中稳定且出现真实消费者后，再建立类型化 Input。

### 7.3 CapabilityResult

CapabilityResult 保持统一信封和明确状态语义：

```text
CapabilityResult
├── request_id / capability_id
├── status
├── outputs[]
├── evidence_refs[]
├── rule_result_refs[]
├── missing_information[]
├── errors[]
├── limitations[]
├── quality?
└── execution_meta?
```

`CapabilityOutput` 提供 output ID、类型、摘要、可选最小 payload 和证据引用；稳定复杂产物应优先拥有独立领域对象并通过引用返回。`CapabilityExecutionMeta.trace_id` 只关联 Runtime Trace，不复制运行细节。

### 7.4 六种状态

| 状态 | 精确定义 | 后续含义 |
| --- | --- | --- |
| `SUCCESS` | 核心结果完整产生 | 继续或完成 |
| `PARTIAL_SUCCESS` | 已有可用结果，但存在错误、缺失或限制 | 继续或评估后重规划 |
| `NEED_INFORMATION` | 缺少可靠处理所需信息 | 获取可信信息或询问用户 |
| `BLOCKED` | 确定性业务规则阻止当前动作 | 停止受阻动作，不能绕过 |
| `NO_RESULT` | 请求合法且执行正常，但没有业务结果 | 调整条件、重规划或正常结束 |
| `FAILED` | Capability 未能正常完成 | 由 Application 决定停止、降级或有限重试 |

状态不变量：

1. `FAILED` 必须至少有一个 Error。
2. `BLOCKED` 必须至少引用一个 Rule Result。
3. `NEED_INFORMATION` 必须说明缺失信息。
4. `SUCCESS` 不得携带 Error。
5. `PARTIAL_SUCCESS` 必须通过 Error、MissingInformation 或 limitation 说明不完整之处。
6. `NO_RESULT` 不是失败，不能靠空列表猜状态。
7. 业务无权经营是 `BLOCKED`；规则服务超时是 `FAILED/TIMEOUT`。
8. 原始 Exception、traceback、Token、Prompt 和内部地址不进入 Domain Result。

## 8. Plan Contract

Plan 是针对 Goal 的版本化当前行动意图，不是 Workflow Engine，也不负责执行。

### 8.1 当前结构

```text
Plan
├── plan_id / version
├── goal_ref
├── status
├── steps[]
└── supersedes_version?

PlanStep
├── step_id
├── capability_id
└── depends_on[]
```

PlanStatus 只描述计划生命周期：`ACTIVE`、`COMPLETED`、`BLOCKED`、`SUPERSEDED`、`CANCELLED`。Capability 的一次失败不自动等于整个 Plan 失败。

### 8.2 不变量

1. Plan 关联明确 Goal 版本，版本从 1 开始；修订保持 `plan_id` 并递增版本。
2. `supersedes_version` 必须低于当前版本。
3. PlanStep 选择 Capability，不直接选择底层 Tool。
4. 步骤依赖通过 `depends_on` 表达，不使用固定步骤号。
5. 允许只出现部分 Capability，也允许同一 Capability 多次出现。
6. step ID 唯一，依赖目标必须存在，步骤不能依赖自己，依赖图不能成环。
7. Plan 不包含 Tool 参数、Prompt、Trace、客户事实、权限裁决、`if/else`、循环或 retry DSL。
8. PlanStep 不保存第二套运行状态；是否 Ready 由 Application 根据步骤结果计算。
9. 写操作的规则校验和用户确认来自可信 Capability Policy/执行策略，不由 LLM 在 PlanStep 中自由生成或省略。
10. Replan 产生完整 Plan 新版本，保留仍有效的成功结果，不静默修改旧版本。

## 9. 统一引用

`GoalRef` 和 `PlanRef` 统一使用 `id + version`。引用对象必须校验非空 ID 和正版本号，避免 Opportunity、CapabilityRequest 等对象各自发明不同的 Goal/Plan 链接类型。

## 10. 契约验证矩阵

| 对象 | 机器可强制 | Review 强制 |
| --- | --- | --- |
| Goal | ID、版本、原始请求、不可变修订 | 不臆造事实、不混入 Plan 或 Demo 特例 |
| Evidence | Source、类型、时间区间、置信度范围 | 模型/经验不得冒充事实或规则 |
| Opportunity | GoalRef、EvidenceLink、优先级理由配对 | 问题判断不得退化为产品推荐或客户标签 |
| CapabilityRequest | 身份、GoalRef、可信 actor 来源 | 输入只携带必要引用，不扩大敏感数据 |
| CapabilityResult | 六种状态不变量 | 规则裁决不可被模型覆盖 |
| Plan | 版本、唯一 step、依赖存在、无环 | 不退化为固定五步或第二套 Workflow Engine |
| 架构 | Domain 不导入 Agent/Model | Capability 与 Tool、业务状态与 Runtime 状态保持分离 |

当前自动化测试还覆盖：非 Demo 产品、非开门红场景、单 Capability Plan、重复 Capability、并行依赖、Goal 修订、正常无结果、缺信息、规则阻断和技术失败。

## 11. M1 验收结论

M1 交付的是最小、透明、可替换的领域契约，而不是完整业务功能。满足以下条件即视为成立：

- 任意量化或非量化经营诉求均可由 Goal 表达；
- 信息缺失和假设可显式存在；
- 事实、规则、模型信号、经验和 Agent 判断保持边界；
- Opportunity 脱离开门红和具体产品仍成立；
- Capability 与 Tool 明确分离，内部实现可替换；
- 状态能区分无结果、缺信息、规则阻断和运行失败；
- Plan 可跳过、重复、重排 Capability，并支持轻量依赖和版本修订；
- Domain 没有反向污染 Agent/Model Runtime。

## 12. 未来可新增的契约细节

下列内容是允许的演进方向，不是当前待办，也不得仅因“以后可能需要”提前加入。新增时必须同时给出真实消费者、数据来源、状态语义、验证规则和迁移策略。

### 12.1 Goal：非量化完成与复杂目标

触发条件：Tracking 需要确定性判断某个非量化 Goal 是否完成，且无法由 `metric + target` 推导。

可新增：

- `completion_criteria`：只描述交付物或复合完成条件；
- `SubGoal` 与贡献关系：仅在复杂目标拆解成为真实需求后引入；
- Metric Definition/version 引用：仅在指标口径存在多版本且被校验或追踪消费时引入。

禁止恢复与 Target 同义的量化完成文本，避免双写不一致。

### 12.2 Evidence：来源记录、冲突与数据质量

触发条件：生产审计需要精确回查原记录，或 Capability 确实根据冲突/完整度采取不同动作。

可新增：

- `record_ref/source_ref`：引用源系统记录，不复制完整源对象；
- 类型化 Evidence Value：某类证据出现稳定结构和多个消费者后建立；
- `EvidenceConflict` 或 EvidenceSet：需要机器化处理多个权威来源冲突时建立；
- 数据获取完整度：优先放在采集结果或 CapabilityResult，而不是恢复统一 EvidenceQuality。

### 12.3 Opportunity：圈客、排序与持续有效性

触发条件及归属：

- M5 Targeting：新增独立 `CandidateCriteria`，由 Opportunity + Evidence 生成，并记录到平台查询条件的映射；不把 SQL/平台 DSL 放回 Opportunity。
- 多 Opportunity 排序：只有排序消费者需要因子级解释时，新增类型化 `PriorityAssessment/PriorityFactor`。
- M7 Tracking：新增 `OpportunityValidity`、失效条件、重新评估原因和生命周期版本。
- 目标贡献：只有可信估计模型或追踪逻辑实际消费时，新增结构化 Goal Contribution；模型不可随手生成贡献金额。

不新增执行型 `next_action_hint`；下一步仍由 Planner 决定。

### 12.4 Capability：类型化输入、写操作策略与审计

触发条件及可新增内容：

- 某能力出现稳定复杂输入：保留统一 CapabilityRequest 信封，为该 capability 增加受控类型化 Input；
- M6 真实写操作：在可信 CapabilityDefinition/Policy 中增加 `operation_type`、`required_controls`、幂等要求和授权策略；执行器确定性强制，不依赖 Plan 文本；
- 生产版本治理：增加输入/输出 schema version、Tool/模型/规则/知识/特征版本；
- 异步执行：只有真实异步任务出现后增加 `PENDING/CANCELLED` 等状态及 job reference；
- 稳定输出对象：建立 CandidateSet、Strategy、RuleDecision、OperationTask 等独立 Contract，并让 CapabilityOutput 优先返回引用；
- 请求级约束：仅当执行器有明确校验和消费逻辑时新增类型化约束，不恢复万能 dict。

### 12.5 Plan：解释、持久运行与控制展示

触发条件及可新增内容：

- 前端需要稳定展示且 Planner 输出经过验证：可增加简洁 `objective/reason`；不得保存模型内部推理。
- Application 需要校验计划输入/输出：可增加受控 `input_refs/expected_outputs`，但只有在执行映射或完成判断真实消费时引入。
- 持久运行、恢复或并发：在独立运行状态中增加 step runtime status、attempt、lease、resume token；不把可变状态塞回不可变 PlanStep。
- 用户界面展示控制要求：Plan 可以引用可信 Capability Policy 解析出的控制项，但模型不能降低或取消 required controls。
- 更完整版本谱系：只有局部替换追踪不足时，增加 `replaced_step_ref` 或 disposition；不提前引入 Workflow DSL。

### 12.6 新领域产物

CandidateSet、Strategy、RuleDecision、OperationTask、TrackingEvent 和 GoalProgress 应在对应 Capability 出现真实输入输出需求时分别设计。它们需要遵循同一原则：

- 事实、规则、模型信号和 Agent 建议分层；
- 通过版本化引用关联，不复制大对象；
- 写操作由确定性策略控制；
- 先证明现有 Contract 无法覆盖，再新增抽象。

## 13. 演进评审清单

未来任何 Domain 字段或类型变更，在合入前至少回答：

1. 当前哪个消费者必须读取它？
2. 不新增它会导致什么可复现的错误或关键语义丢失？
3. 它属于核心对象，还是属于 Targeting、Validation、Tracking、审计或运行状态？
4. 数据来自事实、规则、模型还是 Agent 建议？来源和版本如何保存？
5. 是否与已有字段重复，是否会产生双写一致性问题？
6. 是否能用稳定引用代替开放式 payload 或完整对象复制？
7. 哪些不变量由代码强制，哪些只能由架构评审保证？
8. 是否同步更新 Contract Test、`current-state.md`、`architecture.md` 和 `dev-log.md`？

只有这些问题有明确答案，未来契约细节才应进入核心 Domain。
