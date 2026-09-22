# Replan 收敛设计

状态：已延后；不属于当前 Demo 实施范围

> 2026-09-21 用户明确要求 Demo 不构建 Replan，只执行一次计划，完成 Goal 分析、机会发现、圈客和策略执行。本文保留为后续参考，以下“首版”“最多一次 Replan”“已确认事项”和验收清单均不得作为当前开发指令。已有代码的重规划路径应在后续首版实现中断开；本次文档调整不代表代码已禁用。项目级范围见 AGENTS.md。

## 1. 文档定位

本文用于收敛 Replan 的触发、输入快照、成功结果保留、失败步骤处理、Plan 换版、确定性校验、循环限制和审计边界。

本文建立在以下待确认设计之上：

- `2026-09-21-planner-convergence.md`：首次规划和共享 Planner 基础；
- `2026-09-21-capability-artifact-flow.md`：执行历史、可复用产物和后继输入解析。

本文是候选设计，不覆盖当前代码、`doc/current-state.md`、`doc/architecture.md` 或 M1 Domain Contract。未确认方案不得直接视为实现要求，也不得据此宣称当前系统已具备完整局部重规划能力。

## 2. 当前事实

当前 Replan 已经具备以下最小能力：

- 复用同一个 Planner，通过独立入口生成 Plan 新版本；
- 只有 CapabilityResult 为 `NO_RESULT` 时允许 Replan；
- 模型接收 Goal、当前 Plan、known context、全部 step results、最近结果和 Capability Catalog；
- 模型返回完整步骤集合，不使用 PlanPatch；
- 新 Plan 保持 plan ID、版本加一并记录 `supersedes_version`；
- 基础 Plan Validation 继续检查 Catalog、step ID、依赖和环；
- Replan Validation 阻止已成功旧 step ID 被复用为不同 Capability；
- ExecutionContext 保留旧 step results，使新 Plan 中保留的成功步骤不会重跑；
- 同一 Capability 可以用新的 step ID 再次执行；
- BusinessAgent 最多允许一次 Replan。

当前已知缺口包括：

- Replan 触发原因没有结构化表达；
- 触发范围仅覆盖 `NO_RESULT`；
- 模型直接读取开放式 Context 和完整 Result；
- 成功产物尚未进入可复用的运行产物索引；
- 成功结果是否仍有效主要由 Prompt 判断；
- `NO_RESULT` 旧 step ID 不得进入新 Plan 只由 Prompt 约束；
- BLOCKED、Goal 修改、外部状态变化和产物失效没有 Replan 路径；
- 技术失败与路径不可用没有稳定区分；
- 新 Plan 是否与旧 Plan 实质相同没有校验；
- Plan 换版前后没有原子切换语义；
- ExecutionContext 不保存 Plan 版本历史；
- 旧 Plan 的 SUPERSEDED 生命周期没有完整表达；
- Replan 真实模型验证尚未完成。

## 3. 目标与非目标

### 3.1 目标

- 继续复用同一个 Planner，不新增 Replanner Agent 或第二套规划框架。
- 由确定性策略决定是否触发 Replan、保留什么和禁止绕过什么。
- 让模型只负责在受控状态下重新生成剩余行动路径。
- 保留已确认事实、仍有效成功产物和不可绕过的规则裁决。
- 使失败、无结果和阻断步骤退出新的活动依赖链。
- 通过完整 Plan 新版本表达 Replan，不引入 PlanPatch DSL。
- 确保候选 Plan 完成全部校验后才原子替换 current plan。
- 防止无实质变化的重复规划和无限循环。
- 保留最小 Plan 版本历史和 Replan 审计信息。
- 为后续 Goal 修订、外部状态变化和恢复机制保留扩展边界。

### 3.2 非目标

- 不实现完全自治或无限次数 Replan。
- 不把技术失败统一交给 Planner 绕过。
- 不让模型推翻 Rule Result、权限、归属或渠道限制。
- 不引入多 Agent、Replan Engine、候选 Plan 搜索或复杂 Workflow 框架。
- 不在 PlanStep 中加入 retry、if/else、循环或业务 payload。
- 不在本文中设计完整 Retry、Fallback 或 Resume 机制。
- 不把 Goal 修改简单等同于同 Goal 版本内的执行 Replan。
- 不预先实现全部 Replan Trigger；首版继续保持收敛范围。

## 4. 核心流程

候选 Replan 流程是：

```text
Capability 执行或可信外部事件
              ↓
确定性策略判断是否允许 Replan
              ↓
生成结构化 Replan Trigger
              ↓
构造受控 Replan Snapshot
              ↓
Planner 生成完整 Plan 新版本草案
              ↓
Application 校验身份、产物、规则和可执行性
              ↓
原子切换 current plan
              ↓
复用现有执行循环继续运行
```

模型不能决定是否触发 Replan，也不能在校验完成前改变 ExecutionContext。

## 5. 职责边界

### 5.1 确定性策略职责

Application Policy 负责：

- 判断当前事件是否允许 Replan；
- 生成结构化触发原因；
- 判断成功产物是否仍有效；
- 标记失效产物；
- 保留不可绕过的规则结果；
- 确定当前可用 Capability；
- 管理 Replan 次数预算；
- 判断是否必须先询问用户；
- 校验新 Plan 是否可以替换旧 Plan。

### 5.2 模型职责

模型负责：

- 根据当前 Goal 和有效产物选择剩余路径；
- 跳过已经完成且无需重复的能力；
- 在条件已经变化时重新调用同一 Capability；
- 调整步骤顺序和控制依赖；
- 从当前可用 Capability 中选择合法替代路径；
- 只加入完成剩余 Goal 所需的最少步骤。

### 5.3 模型禁止事项

模型不得决定：

- 是否触发 Replan；
- 是否忽略 BLOCKED Rule Result；
- 成功产物是否仍有效；
- Replan 次数上限；
- Plan ID、版本和 GoalRef；
- 正式新 step ID；
- 是否清除执行历史；
- 是否降低写操作控制策略；
- 是否把技术失败解释成正常无结果。

## 6. 结构化 Replan Trigger

不建议只把最近 CapabilityResult 直接交给 Planner。候选 Replan Trigger 至少表达：

```text
Replan Trigger
├── reason
├── source_step_id?
├── source_request_id?
├── source_result_status?
├── affected_artifact_refs[]
├── invalidated_artifact_refs[]
├── blocking_rule_refs[]
├── goal_ref
├── current_plan_ref
└── automatic_allowed
```

候选 reason 包括：

- `NO_RESULT`；
- `PARTIAL_RESULT_INSUFFICIENT`；
- `RULE_BLOCKED_PATH`；
- `GOAL_REVISED`；
- `USER_CORRECTION`；
- `ARTIFACT_INVALIDATED`；
- `EXTERNAL_STATE_CHANGED`；
- `CAPABILITY_UNAVAILABLE`；
- `EVIDENCE_CONFLICT`。

Trigger 属于 Application 运行契约，不进入 M1 Plan Domain。首版不要求支持全部 reason，但需要保留稳定扩展边界。

## 7. Replan 触发矩阵

候选默认行为如下：

| 事件 | 默认动作 | 是否 Replan |
| --- | --- | --- |
| `SUCCESS` | 继续或完成 | 否 |
| `PARTIAL_SUCCESS` 且结果足够 | 继续 | 否 |
| `PARTIAL_SUCCESS` 且结果不足 | 保留可用产物并调整剩余路径 | 可以 |
| `NO_RESULT` | 调整条件或路径 | 是 |
| `NEED_INFORMATION` | 暂停并获取可信信息 | 否 |
| `BLOCKED` | 保留裁决并评估合法剩余路径 | 有条件 |
| `FAILED` | 进入失败、重试或降级策略 | 默认否 |
| Goal 修改 | 按新 Goal 重新规划 | 是，但不等同普通执行 Replan |
| 用户修正 | 更新可信状态后重新规划 | 是 |
| 产物失效 | 移除失效产物后重新规划 | 是 |
| 外部状态更新 | 重新评估剩余路径 | 可以 |
| 证据冲突 | 保留冲突并停止依赖冲突结论 | 可以 |

### 7.1 NEED_INFORMATION

缺少信息时不得在没有新事实的情况下反复规划。候选流程是暂停、返回 MissingInformation、取得用户或可信服务补充后，再决定恢复还是 Replan。

### 7.2 FAILED

技术失败默认不触发 Replan。Application 应先区分重试、替代实现、Capability 暂时不可用和必须停止。只有 Capability 被确定性标记为不可用且存在合法替代路径时，才形成相应 Replan Trigger。

### 7.3 BLOCKED

BLOCKED 不能成为模型绕过规则的入口。允许 Replan 的前提是：

- Rule Result 继续保留；
- 被禁止的对象、动作或渠道继续禁止；
- 新 Plan 只寻找不违反规则的剩余路径；
- 如果完成 Goal 必须依赖被禁止动作，则 Plan 应进入 BLOCKED。

## 8. Replan Snapshot

模型不应直接读取开放式 ExecutionContext。候选 Snapshot 包括：

```text
Replan Snapshot
├── current_goal
├── current_plan
├── trigger
├── completed_steps
├── reusable_artifacts
├── invalidated_artifacts
├── unsuccessful_step_summaries
├── immutable_rule_results
├── current_capability_view
├── remaining_replan_budget
└── planning_as_of
```

Snapshot 只保留当前规划所需的最小信息。模型不需要看到完整业务 payload、原始异常、traceback、Token、内部地址、敏感 Prompt 或与当前 Goal 无关的数据。

Planner 可见的是执行状态摘要和类型化引用；真实对象继续由 Capability 在执行时通过受控引用加载。

## 9. Plan 换版方式

候选方向继续遵循 M1 Contract：Replan 产生完整 Plan 新版本，不引入 PlanPatch。

“局部重规划”表示：

- 已确认事实不重新计算；
- 仍有效成功产物继续复用；
- 只调整剩余行动路径；
- 已完成步骤不会重复执行。

新 Plan 应保持：

```text
plan_id             不变
version             递增
goal_ref            指向当前 Goal
supersedes_version  指向旧 Plan 版本
status              ACTIVE
steps               完整的新步骤集合
```

Replan 原因、保留产物、失效产物和差异摘要进入运行 Trace 或审计记录，不扩大 Plan Domain。

## 10. 旧步骤分类处理

### 10.1 成功且仍有效

对于 `SUCCESS` 或可接受的 `PARTIAL_SUCCESS`：

- 保留旧 step ID 时 capability ID 不得改变；
- 保留后不得重新执行；
- 有效产物继续存在于 ExecutionContext；
- 新 Plan 不再需要展示该步骤时可以省略；
- 新步骤可以直接消费其产物，不需要依赖被省略的旧步骤。

候选建议是：只有仍对新 Plan 的控制依赖或用户可理解性有价值时才保留成功步骤；步骤被省略不能导致成功产物丢失。

### 10.2 NO_RESULT

- 旧 step ID 不得出现在新活动 Plan；
- 新步骤不得依赖旧 step ID；
- 该步骤不发布可复用普通业务产物；
- 重新调用同一 Capability 必须使用新 step ID；
- 新调用应有输入、范围、实现或可信 Context 变化，不能只更换 ID。

### 10.3 FAILED

- 旧 step ID 不进入新活动依赖链；
- 原错误保留在执行历史；
- 未经失败策略确认，Planner 不能直接重新调用同一不可用实现；
- 合法替代 Capability 必须来自当前 Capability View。

### 10.4 BLOCKED

- 旧 step ID 不进入新活动依赖链；
- Rule Result 保留为不可绕过约束；
- 新 Plan 不得对相同对象和动作绕过阻断；
- 只有存在合法剩余路径时才允许 Replan；
- 否则 Plan 进入 BLOCKED。

## 11. 成功产物与成功步骤分离

Replan 应同时保留成功执行事实和仍有效业务产物，但二者不必始终一起出现在新 Plan 中。

示例：

```text
Plan V1
s1 insight   → opportunity:opportunity_001
s2 targeting → NO_RESULT

Plan V2
s4 targeting → 使用 opportunity:opportunity_001
s5 strategy
```

Plan V2 可以省略 s1。Opportunity 通过 ExecutionContext 的可用产物索引继续存在，而不是依赖 s1 必须被复制到每个新 Plan。

如果 V2 保留 s1，则已有成功 step result 必须阻止其重复执行。

## 12. Goal 修订与执行 Replan

需要区分：

- **同一 Goal 版本内的执行 Replan**：默认可以复用仍有效成功产物；
- **Goal 修订后的重新规划**：必须先重新验证旧产物是否仍适用于新 Goal 版本。

Goal 版本变化后，新 Plan 的 GoalRef 必须指向新版本。旧产物不能仅因为之前成功就默认继续使用。

两类流程可以复用 Planner、Capability View、Plan Builder 和 Validation，但触发原因、产物有效性和审计语义不同。

## 13. Replan Validation

候选 Plan 除执行基础 Plan Validation 外，还应检查：

1. plan ID 与旧 Plan 相同；
2. 版本严格递增；
3. `supersedes_version` 指向旧版本；
4. GoalRef 指向当前 Goal；
5. 保留的成功 step ID 没有改变 capability ID；
6. NO_RESULT、FAILED 和 BLOCKED 的旧 step ID 没有进入新活动 Plan；
7. 新步骤没有依赖上述失败步骤；
8. 失效产物没有成为新步骤输入；
9. 新 Capability 当前可用；
10. 新 Plan 输入来源可满足；
11. Rule Result 和写操作控制策略未被绕过；
12. 已完成步骤不会被作为新步骤重复执行；
13. 重新调用同一 Capability 时使用新 step ID；
14. 新 Plan 至少存在一个可执行起点，或形成明确终止结果；
15. 新 Plan 与旧 Plan 的剩余路径存在实质差异。

当前 Validation 只覆盖其中很小一部分。新增校验范围必须与产物注册、Capability 输入输出边界和当前可用性信息同步，不能通过硬编码 Demo 顺序实现。

## 14. 防止无意义循环

### 14.1 Replan 预算

次数由 Application Policy 管理，不进入 Prompt。Demo 首版可以继续限制为一次，但应从 BusinessAgent 的散落分支提升为明确运行策略。

### 14.2 Plan 指纹

候选方案是对剩余计划结构计算规范化指纹，忽略 Plan ID、版本和正式 step ID，关注：

- capability ID；
- 依赖结构；
- 使用的输入类型；
- 关键执行范围。

如果 Context 没有变化且新旧剩余路径实质相同，应拒绝切换。

### 14.3 重复 Capability 条件

同一 Capability 可以重复调用，但至少应存在以下一种变化：

- 输入引用变化；
- 对象范围变化；
- Capability 版本或实现变化；
- 新增可信信息；
- 前一次失败或无结果原因已被消除。

不能只通过更换 step ID 证明路径已经变化。

## 15. 原子切换和失败处理

候选切换过程是：

```text
构造 Snapshot
→ 模型生成草案
→ 构造候选 Plan
→ 完成全部校验
→ 原子切换 current plan
```

全部校验完成前：

- current plan 保持旧版本；
- 旧步骤结果和成功产物保持不变；
- Replan 失败不能留下半个新 Plan；
- 不允许部分更新依赖或运行状态。

模型调用失败或候选 Plan 非法时，候选处理是：

- 记录一次失败的 Replan 尝试；
- 不切换 Plan；
- 保留完整 ExecutionContext；
- 返回应用级 FAILED 或 STOPPED；
- 不自动无限修复或重试。

一次通过前置校验并实际开始的 Replan 模型生成尝试，即消耗 Replan 预算，无论最终因模型失败或候选校验失败而未切换 Plan；未发起模型调用的 Trigger 或 Snapshot 前置校验失败不消耗预算。审计必须区分“尝试失败”和“成功切换”，以防模型协议错误形成循环，同时保留失败原因。

## 16. Plan 历史和审计

Replan 至少需要保留：

```text
Plan V1
Replan Trigger
Replan Attempt
Plan V2（如果成功）
```

审计信息候选包括：

- 触发原因；
- 触发步骤和结果引用；
- 保留和失效的产物；
- 新增、移除和保留的步骤摘要；
- Replan 校验结果；
- 时间、主体和模型调用引用；
- 是否成功切换 Plan。

当前阶段不一定建设持久化 Repository，但内存运行状态不能在切换新 Plan 后完全丢失旧版本。

旧 Plan 的 `SUPERSEDED` 由 Plan 版本链和成功 Replan 的审计事件推导，不原地修改不可变的旧 Plan 内容。运行视图可以将 V1 呈现为 `SUPERSEDED`；V2 的 `supersedes_version=1` 与成功切换记录共同构成该事实。

## 17. Replan 后继续执行

新 Plan 切换后：

1. ExecutionContext 保留已有 step results；
2. 保留仍有效的产物注册表；
3. 更新 current plan；
4. 根据新 Plan 重新寻找第一个 Ready Step；
5. 保留的成功步骤不会重新执行；
6. 新步骤按输入边界消费已有产物；
7. 失败旧步骤不会释放新依赖；
8. Continuation Policy 继续处理新结果。

BusinessAgent 不应为 Replan 创建第二套执行循环。

## 18. 内部职责候选方案

不建议新增 Replanner 类或 Replan Agent。候选职责分布是：

- Continuation Policy 判断是否进入 Replan 候选；
- Replan Policy 生成 Trigger、预算和不可绕过约束；
- ExecutionContext 提供执行历史、产物和 Plan 版本信息；
- Planner 使用共享规划基础生成 Plan 新版本草案；
- Plan Validation 检查基础 Plan 和 Replan 特有不变量；
- BusinessAgent 在校验成功后原子切换 Plan，并继续现有执行循环。

首次规划和 Replan 应复用 Planning Context、Capability View、Plan Draft、Plan Builder 和基础 Validation，只在触发信息、执行快照和跨版本约束上不同。

具体文件和类型在实现前根据已确认设计决定，避免提前建设 Replan Framework。

## 19. 迁移原则

推荐分阶段实施并分别验证：

1. 建立 Replan Trigger 和明确运行 Policy，首版仍只自动处理 NO_RESULT；
2. 使用产物注册和执行历史构造受控 Snapshot；
3. 扩展 Replan Validation，强制失败步骤退出活动依赖链；
4. 增加 Plan 历史、Replan Attempt 和原子切换；
5. 增加结构指纹和重复 Capability 的变化校验；
6. 再依次考虑 PARTIAL_SUCCESS 不足、Capability 不可用、合法 BLOCKED 剩余路径、Goal 修订和外部状态变化。

迁移期间不得同时引入 Retry、Fallback、Resume、多轮自动规划和持久化框架。每增加一种 Trigger，都应先补齐确定性边界和对应逆向测试。

行为变化后需要同步检查：

- `doc/current-state.md` 中 Replan 能力和限制；
- `doc/architecture.md` 中 Trigger、Snapshot、Plan 历史和数据流；
- `dev-log.md` 中行为变化和验证结论。

## 20. 验收场景

后续实现至少应覆盖以下行为：

1. NO_RESULT 形成结构化 Trigger。
2. Plan V2 保持相同 plan ID、版本递增。
3. 成功产物在 V2 中继续存在。
4. 保留的成功 step 不会重跑。
5. 成功 step ID 不能更换 capability ID。
6. NO_RESULT 旧 step ID 不能进入 V2。
7. 新步骤不能依赖 NO_RESULT 旧步骤。
8. 同一 Capability 再次执行必须使用新 step ID。
9. 同一 Capability 无输入、范围或实现变化时不能无意义重复。
10. NEED_INFORMATION 不触发 Replan。
11. 普通技术 FAILED 不触发 Replan。
12. BLOCKED Rule Result 不能被新 Plan 绕过。
13. 存在合法剩余路径时，BLOCKED 可以触发受约束 Replan。
14. 不存在合法路径时 Plan 进入 BLOCKED。
15. 失效产物不能进入 V2。
16. Goal 版本变化后旧产物不会默认复用。
17. 新 Plan 与旧剩余计划实质相同时被拒绝。
18. 达到 Replan 上限后停止。
19. 模型失败时 current plan 不变。
20. 候选 Plan 校验失败时 current plan 不变。
21. Replan 成功后原子切换并继续执行。
22. Plan V1、Trigger、Attempt 和 Plan V2 可以回放。
23. 非 Demo Goal 使用同一 Replan 机制。
24. 不新增独立 Replanner Agent 或第二套执行循环。

## 21. 风险与取舍

- 结构化 Trigger 提高可审计性，但会增加 Application 运行契约，需要保持其不进入 Domain Plan。
- 完整 Plan 新版本比 Patch 简单稳定，但需要明确成功步骤是否保留以及如何展示历史。
- 成功产物独立于步骤可以避免重复执行，但要求产物注册表具有可靠血缘和有效性。
- 对 BLOCKED 允许受约束 Replan 能支持合法剩余路径，也带来绕过规则风险，因此必须先有确定性 Policy。
- Plan 指纹可以防止明显循环，但不能证明新 Plan 的经营语义一定更优。
- 将失败 Replan 尝试计入预算有利于防循环，但可能降低偶发模型格式错误后的恢复机会。
- Goal 修订与执行 Replan 共用基础设施有利于复用，但不能混淆二者的产物有效性语义。

## 22. 已确认事项

1. Replan 复用同一个 Planner，不新增 Replanner 或第二套规划框架；通过完整 Plan 新版本表达变更，不使用 PlanPatch。
2. 引入 Application 层的结构化 Replan Trigger；模型只根据受控 Replan Snapshot 生成剩余路径，不能决定触发时机、版本身份、产物有效性或规则例外。
3. Demo 首版仅自动处理 `NO_RESULT`。`PARTIAL_SUCCESS` 仅在确定性策略判定已发布产物不足以完成剩余路径时才可触发 Replan；`NEED_INFORMATION` 先暂停并补齐可信信息，不 Replan。
4. `FAILED` 默认不 Replan；Retry/Fallback 尚未设计或确认前按停止处理。只有 Capability 被确定性标记为不可用且存在合法替代路径时，后续阶段才可增加相应 Trigger。
5. `BLOCKED` 只允许在完整保留 Rule Result、且新路径不触犯原裁决时进行受约束 Replan；不存在合法剩余路径时整体进入 `BLOCKED`。
6. 仍有效的成功产物独立于旧步骤继续保留；成功步骤可以从新 Plan 省略。`NO_RESULT`、`FAILED` 和 `BLOCKED` 的旧 step ID 禁止进入新活动 Plan 或成为新步骤依赖；同一 Capability 的重新调用必须使用 Application 分配的新 step ID，并具有输入、范围、实现或可信 Context 的实质变化。
7. 采用忽略 Plan 身份和正式 step ID 的剩余路径指纹，拒绝 Context 未变化时无实质差异的新 Plan；Plan 仅在全部校验成功后原子切换。
8. 保存最小 Plan 版本历史、Replan Trigger、Replan Attempt、校验结果和切换结果，以支持回放；切换后不能丢失旧版本、执行历史或仍有效产物。
9. Demo 首版最多一次 Replan，由显式运行 Policy 管理，而不是散落在 BusinessAgent 分支中。
10. Goal 修订与同 Goal 版本内的执行 Replan 分开处理：两者可复用 Planner 基础设施，但 Goal 修订后的旧产物必须重新验证后才可使用。
11. Trigger 按阶段开放；在首版 `NO_RESULT` 稳定后，才依次评估 `PARTIAL_SUCCESS` 不足、Capability 不可用、合法 BLOCKED 剩余路径、Goal 修订和外部状态变化。
12. 通过前置校验并实际开始的 Replan 模型生成尝试消耗预算，即使模型或候选校验失败；未发起模型调用的 Trigger/Snapshot 前置校验失败不消耗预算。审计明确区分尝试失败和成功切换。
13. `SUPERSEDED` 由不可变 Plan 的版本链和成功切换审计事件推导；运行视图可以呈现旧版本为 `SUPERSEDED`，但不原地修改旧 Plan。

## 23. 成功标准

- 新会话只阅读当前事实源、M1 Contract、Planner 设计、产物流转设计和本文即可理解 Replan 的问题与候选边界。
- 模型不能决定触发时机、产物有效性、规则例外或版本身份。
- 新 Plan 只在所有校验完成后原子替换旧 Plan。
- 有效成功产物能够跨 Plan 版本复用，失败步骤不会进入新活动依赖链。
- BLOCKED Rule Result 不会被模型通过换步骤或换路径绕过。
- 相同 Context 下的无实质变化 Plan 不会形成自动循环。
- Replan 失败不会破坏 current plan、step results 或已发布成功产物。
- Plan 版本、Trigger、Attempt 和结果具备最小可回放信息。
- 首次规划与 Replan 复用同一套规划基础，不产生第二套执行循环或 Replanner Agent。
