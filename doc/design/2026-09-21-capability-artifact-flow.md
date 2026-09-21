# Capability 产物引用流转收敛设计

状态：待确认

## 1. 文档定位

本文用于收敛 `CapabilityResult → ExecutionContext → 后继 CapabilityRequest` 的产物引用流转，明确执行结果、可复用产物、输入解析和运行血缘之间的边界，为 Planner 可执行性校验和后续 Replan 设计提供共同基础。

本文是候选设计，不覆盖当前代码、`doc/current-state.md`、`doc/architecture.md` 或 M1 Domain Contract。未确认的方案不得直接视为实现要求，也不得据此宣称当前系统已经具备真实 Capability 数据闭环。

## 2. 当前事实

当前执行链路已经具备：

- `ExecutionContext` 保存当前 Goal、当前 Plan、`known_context` 和按 step ID 记录的 CapabilityResult；
- `build_capability_request()` 从 Goal、PlanStep 和 ExecutionContext 构造 CapabilityRequest；
- `known_context` 中以 `*_refs` 命名的字符串集合会被转换为 `input_refs`；
- `execute_step()` 调用 CapabilityExecutor，并把结果记录到 `step_results`；
- Ready Step 根据依赖步骤是否取得 `SUCCESS` 或 `PARTIAL_SUCCESS` 判断；
- `NO_RESULT` 可以触发当前最小 Replan。

当前真实数据流是：

```text
初始 known_context ───────────────→ 每个 CapabilityRequest
CapabilityResult ─→ step_results ─╳→ 后继 CapabilityRequest
```

因此当前存在以下缺口：

- `depends_on` 只控制执行顺序，不传递前序步骤产物；
- CapabilityResult 的 outputs 不会进入后继 CapabilityRequest；
- Replan 模型可以看到历史结果，但新步骤不能确定性消费成功产物；
- `known_context` 是开放字典，初始引用、运行产物和其他属性没有稳定边界；
- 没有校验 handler 返回的 request ID 和 capability ID 是否与请求一致；
- 没有校验 output type 是否属于 Capability 声明的可产出类型；
- 没有区分执行历史、可复用产物和审计引用；
- 当前 Fake Capability 不依赖真实输入，因此现有执行测试没有覆盖上述缺口。

## 3. 目标与非目标

### 3.1 目标

- 明确区分步骤执行事实和当前可复用业务产物。
- 只将经过校验的类型化引用发布到运行上下文，不自动合并任意 payload。
- 让后继 CapabilityRequest 根据 Capability 输入边界、Plan 依赖和当前有效产物取得最小引用集。
- 保留产物来源、步骤、请求、Capability、Goal 和 Plan 版本血缘。
- 让 Planner、执行层和 Replan 使用同一套可用产物视图。
- 保证 `NO_RESULT`、失败、缺信息和规则阻断不会被误解释为可复用业务产物。
- 保持 M1 CapabilityRequest/Result 和轻量 PlanStep 边界，不建立 Workflow 变量系统。

### 3.2 非目标

- 不在 ExecutionContext 中复制完整 Opportunity、客户、策略或规则对象。
- 不自动把 CapabilityOutput payload 合并为共享业务事实。
- 不在本文中设计完整业务对象仓库、数据库事务或生产持久化。
- 不引入通用数据映射 DSL、字段级 output binding 或表达式引擎。
- 不让模型决定哪些结果可信、哪些引用可以绕过规则控制。
- 不把 PlanStep 扩展为 Tool 参数或业务数据载体。
- 不在本文中确认 Goal 修改后的完整产物失效和恢复协议。

## 4. 核心数据流

候选流转过程是：

```text
CapabilityResult
      ↓
校验请求关联、状态和输出类型
      ↓
原子记录步骤结果并发布可复用引用
      ↓
ExecutionContext 维护执行事实与可用产物
      ↓
根据后继 Capability 输入边界解析最小引用集
      ↓
CapabilityRequest.input_refs
```

该过程分成三个独立职责：

1. **结果记录**：保存 Capability 实际执行状态和完整结果。
2. **产物发布**：把允许复用的 CapabilityOutput 转换为类型化引用并保存血缘。
3. **输入解析**：为具体后继步骤选择满足输入边界的最小引用集合。

不能继续通过扫描任意 Result payload 或把所有 Context 内容透传给后继 Capability 来替代这些职责。

## 5. ExecutionContext 候选边界

ExecutionContext 需要在概念上区分：

```text
ExecutionContext
├── goal
├── current_plan
├── initial_artifacts
├── produced_artifacts
└── step_results
```

- `initial_artifacts` 表示本次运行开始前已经存在且允许使用的对象引用；
- `produced_artifacts` 表示 Capability 执行后发布的可复用对象引用；
- `step_results` 表示每个步骤的完整执行事实，包括成功、无结果、缺信息、阻断和失败。

实现时可以使用一个带来源信息的统一产物注册表，但不能丢失初始来源和执行来源的区别。

`step_results` 回答“执行过什么以及结果如何”；产物注册表回答“现在有哪些对象可以安全地作为输入”。二者不能相互替代。

## 6. Application 层产物引用

M1 CapabilityRequest 已使用 `type:id` 形式的统一 `input_refs`。ExecutionContext 内部候选记录应至少表达：

```text
Artifact Reference
├── artifact_type
├── artifact_id
├── normalized_ref
├── origin
├── source_step_id?
├── source_request_id?
├── source_capability_id?
├── source_result_status?
├── goal_ref
├── plan_ref?
└── availability
```

该记录属于 Application 运行状态，不是新的业务领域对象。真正的 Opportunity、CustomerSet、Strategy、Evidence 或 Task 仍由对应事实源保存；ExecutionContext 只保存引用和运行血缘。

产物身份与步骤身份必须分离。Plan 换版后，即使生产该产物的旧步骤不再出现在新 Plan 中，只要产物仍有效，其引用仍可继续使用。

## 7. CapabilityResult 的产物发布

### 7.1 发布来源

默认只有明确的 `CapabilityOutput` 可以发布普通业务产物。Application 使用 `output_type + output_id` 形成规范化引用，例如：

```text
output_type = opportunity
output_id   = opportunity_001
       ↓
opportunity:opportunity_001
```

不得从 Capability ID、summary 或 payload 内容猜测产物类型。

### 7.2 输出类型约束

Capability 返回的 output type 必须属于该 Capability 声明的可产出类型。未声明或无法识别的 output type 不能进入可用产物注册表。

这要求 Capability 的 Planner/Execution 可见元数据至少能够表达可接受输入类型和可产出类型。本文不预先确认最终元数据 Schema。

### 7.3 Payload 边界

CapabilityOutput payload 可以承载当前结果所需的最小展示或适配信息，但不能自动执行以下操作：

```text
known_context ← merge(output.payload)
```

后继 Capability 应通过类型化引用从权威存储加载所需对象。禁止自动合并 payload 的原因包括：

- 无法区分事实、模型信号和建议；
- 共享字段覆盖不可审计；
- 容易扩大客户敏感数据传播；
- 下游会隐式依赖上游内部结构；
- 版本、来源和冲突无法稳定处理。

## 8. Result 状态与发布矩阵

候选默认规则如下：

| Result 状态 | 记录 step result | 发布普通业务产物 | 说明 |
| --- | --- | --- | --- |
| `SUCCESS` | 是 | 是 | 发布通过校验的明确输出 |
| `PARTIAL_SUCCESS` | 是 | 是 | 保留部分成功、质量和限制标记 |
| `NO_RESULT` | 是 | 否 | 没有新的业务产物，可触发 Replan |
| `NEED_INFORMATION` | 是 | 否 | 返回缺失信息，不发布业务产物 |
| `BLOCKED` | 是 | 否 | Rule Result 进入审计和血缘，不作为普通产物绕过阻断 |
| `FAILED` | 是 | 否 | Error 进入执行历史，不发布业务产物 |

### 8.1 PARTIAL_SUCCESS

当前 Continuation Policy 允许 `PARTIAL_SUCCESS` 释放依赖，因此其明确输出也应可以发布，但产物记录必须保留：

- 来源状态为部分成功；
- limitations；
- quality；
- missing information 或局部错误。

后继 Capability 是否接受部分成功产物，应由其输入策略决定。首版候选规则是默认允许使用明确输出，但不得丢失部分成功标记。

### 8.2 Evidence

需要区分：

- Capability 明确产出的 Evidence；
- 仅用于说明本次结果依据的 evidence refs。

前者可以作为明确输出注册，后者默认只保留在结果血缘中，不自动传入所有后继 Capability。

### 8.3 Rule Result

规则阻断引用默认只作为审计和血缘信息。除非某项后续能力明确声明合法消费 Rule Result，否则不得将其作为普通输入推动另一条路径绕过裁决。

## 9. 结果关联和原子更新

Application 在记录结果和发布产物前，候选校验包括：

1. Result request ID 与本次 CapabilityRequest 一致；
2. Result capability ID 与本次 CapabilityRequest 一致；
3. Result 满足 M1 状态不变量；
4. output ID 和 output type 非空且符合格式；
5. output type 属于 Capability 声明的可产出类型；
6. 同一规范化引用不存在类型或来源冲突；
7. 当前 Result 状态允许发布产物。

记录 step result 和发布产物应作为一个 Application 原子操作，避免出现结果已记录但部分产物写入失败，或产物已发布但没有对应执行事实。

当前内存版实现不需要因此引入数据库事务框架，但需要保证单次状态更新的一致性。

## 10. 后继输入解析

后继 CapabilityRequest 不应接收 Context 中的全部引用。候选解析过程是：

```text
当前 PlanStep
    ↓
读取 Capability 输入边界
    ↓
从依赖步骤和当前有效产物中寻找匹配引用
    ↓
补充适用的初始产物
    ↓
校验类型、数量和可用性
    ↓
生成最小 input_refs
```

### 10.1 输入来源优先级

候选优先级是：

1. 当前步骤直接依赖步骤产生的匹配产物；
2. 依赖链上仍有效的匹配产物；
3. 初始 Context 中已有的匹配产物。

该规则同时支持：

- 前序 Capability 产生 Opportunity，后继圈客使用该 Opportunity；
- 初始 Context 已有 Opportunity，Plan 直接从圈客开始。

### 10.2 最小数据访问

只有当前 Capability 声明需要或允许的引用才能进入请求。不相关的 Opportunity、Customer、Strategy 或 Task 引用不得因为存在于 Context 就全部透传。

GoalRef 已经由 CapabilityRequest 单独携带，不需要作为普通 input ref 重复传入。

### 10.3 输入不足

找不到必需输入时，Capability 尚未被调用，因此不能伪装成 Capability 执行后的 `NO_RESULT`。该情况属于：

- Plan 可执行性校验失败；
- 执行前 `INFORMATION_REQUIRED`；
- 或 Context 与 Plan 不一致的 Application 错误。

具体对外结果需要与 Planner 统一规划结果一并确认。

## 11. Capability 输入输出边界

为了避免提前建设复杂类型系统，首版候选只表达：

- required input types；
- optional input types；
- produced output types；
- 每种输入是否允许多个引用。

这些信息表达能力边界，不表达固定流程。一个 Capability 只依赖 Goal 时可以没有 required input；已有产物可以使 Planner 跳过某些前置能力。

首版不引入：

- 通用 JSON Schema 数据映射；
- 任意表达式；
- 字段级 output binding；
- 模型生成的输入选择规则；
- Workflow variable。

如果未来同一 Capability 存在多个合法替代输入方案，应在真实消费者出现后再扩展，不应为当前 Demo 预建通用逻辑语言。

## 12. 多引用和歧义

### 12.1 允许多个引用

当 Capability 明确允许消费多个同类引用时，可以按稳定顺序传入作用域内所有匹配引用。

### 12.2 只允许一个引用

当 Capability 只允许一个引用但找到多个候选时，系统不得任意选择第一个。

候选处理顺序是：

- 使用用户请求或当前受控 Context 中明确的对象范围缩小候选；
- 如果仍无法唯一确定，返回结构化信息缺失；
- 不调用 Capability；
- 不让模型静默猜选。

### 12.3 引用冲突

同一规范化引用不能被注册为不同类型或具有冲突来源。来源冲突需要显式保留并进入错误或治理路径，不能由 ExecutionContext 静默覆盖。

## 13. Initial Context 迁移

迁移期可以继续接受当前 `*_refs` 形式，但进入 ExecutionContext 时应立即规范化为类型化引用。

候选规则包括：

- 只接受已知引用键；
- 对字符串引用进行去重和规范化；
- 保留来源为 `initial_context`；
- 非引用开放属性不进入 CapabilityRequest；
- 不允许调用方通过键名伪造可信身份或规则裁决；
- 逐步淘汰运行过程中直接读写任意 `known_context`。

该兼容入口只用于迁移，不应成为长期开放式 Context 协议。

## 14. 与 Planner 的关系

Planner 使用的 Planning Context 应从当前有效产物注册表投影，而不是直接读取任意 `known_context` 或完整 CapabilityResult。

Planner 可见的是：

- 当前有哪些产物类型和引用；
- 产物是否可用；
- 产物与当前 Goal 的关联；
- Capability 的输入输出边界。

Planner 不需要读取完整业务 payload，也不负责重新判定规则结果。

Plan 可执行性校验和运行时输入解析必须使用同一套 Capability 输入输出边界，避免 Planner 判断可执行而执行层又找不到输入。

## 15. 与 Replan 的关系

本方案是 Replan 的前置基础。Replan 需要明确区分：

```text
可复用产物
  └─ 已成功产生、仍然有效的业务引用

执行历史
  └─ SUCCESS、PARTIAL_SUCCESS、NO_RESULT、BLOCKED、FAILED 等步骤结果
```

示例：

```text
Plan V1
s1 directional_insight → SUCCESS
   发布 opportunity:opportunity_001

s2 customer_targeting  → NO_RESULT
   不发布 customer_set
```

Replan 时，Opportunity 是可复用产物，s2 的 NO_RESULT 是执行历史。Plan V2 的新圈客步骤可以使用已有 Opportunity，但不能依赖旧的失败步骤。

即使 Plan V2 不再包含 s1，只要 Opportunity 仍有效，其引用也应独立于旧 step 继续存在。

## 16. Goal 与 Plan 版本变化

每个产物引用应记录产生时的 GoalRef 和 PlanRef。

候选首版规则是：

- 同一 Goal 版本内 Replan，成功产物默认继续有效；
- Plan 版本变化不自动使产物失效；
- Goal 版本变化不能默认继续使用旧产物，需要重新验证；
- 带有效期或受外部状态影响的产物，由其事实源或 Capability 决定是否仍有效；
- Rule Result 不能因为 Plan 换版被模型解释为无效。

Goal 修订后的完整产物重用和失效策略留给后续恢复设计，但本轮必须保留足够血缘。

## 17. 内部职责候选方案

当前相关模块仍较小，不建议立即建设大型 Execution 包。候选职责分布是：

- ExecutionContext 保存当前运行状态和产物索引；
- 独立的产物注册职责完成规范化、校验和发布；
- 独立的输入解析职责根据 Capability 边界生成 input refs；
- Step Execution 组织请求、执行、结果记录和产物发布；
- CapabilityExecutor 继续只负责 handler 分发。

CapabilityExecutor 不承担 Context 更新、输入解析、产物注册、Plan 调度或 Replan。

具体文件名和数量在实现前根据现有代码确认，避免字段级文件碎片或新的运行框架。

## 18. 迁移原则

推荐分阶段实施并分别验证：

1. 建立产物注册和初始引用规范化，不改变 Planner 行为；
2. 增加 Request/Result 关联校验和 Result 产物发布；
3. 为 Capability 增加最小输入输出边界并接入输入解析；
4. 让 Planner Planning Context 和可执行性校验使用同一产物视图；
5. 最后基于执行历史和可复用产物收敛 Replan。

迁移期间应保持 M1 CapabilityRequest/Result 和 PlanStep 契约，不创建第二套业务领域对象，也不把 payload 合并回开放式 Context。

行为变化后需要同步检查：

- `doc/current-state.md` 中执行数据流、CapabilityRequest 和 Replan 限制；
- `doc/architecture.md` 中 ExecutionContext、输入解析和产物流转；
- `dev-log.md` 中功能变化与验证结论。

## 19. 验收场景

后续实现至少应覆盖以下行为：

1. SUCCESS 输出被注册为类型化引用。
2. PARTIAL_SUCCESS 输出被注册并保留部分成功标记。
3. NO_RESULT 不发布普通业务产物。
4. NEED_INFORMATION、BLOCKED 和 FAILED 不发布普通业务产物。
5. BLOCKED 的 Rule Result 被保留用于审计和血缘。
6. Request ID 不一致的 Result 被拒绝。
7. Capability ID 不一致的 Result 被拒绝。
8. 未声明的 output type 不能发布。
9. 后继步骤取得直接依赖步骤的匹配输出。
10. 初始 Context 已有产物时可以跳过前置步骤。
11. 不相关引用不会进入 CapabilityRequest。
12. 同一个引用不会被重复注册。
13. 同一 ID 的类型或来源冲突不会被静默覆盖。
14. 多个输入无法唯一确定时不会任意选择第一个。
15. Capability payload 不会自动写入共享 Context。
16. Replan 后成功产物继续存在。
17. 新 Plan 步骤可以使用旧 Plan 的有效产物。
18. NO_RESULT 步骤不会成为新 Plan 的输入来源。
19. GoalRef 和 PlanRef 血缘能够追踪。
20. 非 `*_refs` 的开放式 Context 不会被透传。

## 20. 风险与取舍

- 产物注册表提高可追溯性，但会引入运行状态和业务对象仓库之间的新边界，需要避免复制事实。
- Capability 输入输出类型太弱无法确定性解析，太强则可能提前建设复杂类型系统。
- 默认发布 PARTIAL_SUCCESS 输出符合当前 Ready 语义，但下游必须能看到质量和限制。
- 直接依赖优先有利于最小输入，但某些业务可能需要依赖链上的更早产物，需要保留受控补充规则。
- 禁止自动 payload 合并会要求真实 Capability 提供可解析引用和对象存储，这是正确的长期方向，但会增加 Demo 适配工作。
- Goal 版本变化后的产物有效性无法仅由执行层判断，必须保留血缘并交给后续恢复策略。

## 21. 待确认事项

实施前需要确认：

1. 是否引入 Application 层产物注册表。
2. 是否明确区分初始产物、运行产物和 step results。
3. 是否只允许明确 CapabilityOutput 发布普通业务产物。
4. SUCCESS 和 PARTIAL_SUCCESS 是否都允许发布明确输出。
5. Evidence 与 Rule Result 默认只作为血缘和审计引用，还是可以自动成为普通输入。
6. Capability 是否增加最小输入输出类型和多值能力声明。
7. 后继输入是否按直接依赖、依赖链、初始 Context 的顺序解析。
8. 多个引用无法唯一确定时是否返回信息缺失，而不是自动选择。
9. 是否确定禁止自动合并 CapabilityOutput payload。
10. Request/Result 关联一致性是否由 Application 强制校验。
11. Plan 换版时成功产物是否独立于旧步骤继续保留。
12. Goal 版本变化时是否默认要求重新验证产物。
13. 输入不足应由规划阶段阻止，还是允许执行前返回统一的信息缺失结果。
14. 产物有效性和引用冲突的首版最小规则是什么。

本文推荐：前十二项采用正文中的候选方向；第十三和第十四项在 Planner 结果与 Replan 设计中共同确认。

## 22. 成功标准

- 新会话只阅读当前事实源、M1 Contract、Planner 设计和本文即可理解执行数据流问题及候选边界。
- CapabilityResult 的执行事实和可复用业务产物不再混为一体。
- 后继 CapabilityRequest 能确定性取得必要且最小的输入引用。
- Result payload、开放式 Context 和不相关引用不会被自动传播。
- 每个运行产物能够追溯到 Goal、Plan、步骤、请求、Capability 和结果状态。
- Planner 可执行性校验与运行时输入解析使用同一套 Capability 边界。
- Replan 能明确区分可复用成功产物和失败执行历史。
- Plan 换版不会因步骤变化而无意丢失仍有效的成功产物。
