# Capability 产物流转 Demo V1 范围与开发说明

状态：已确认首版收缩方向；本文为首版实施依据，待实现、待验证

创建日期：2026-09-21

> 当前 Demo 每次请求只生成并执行一个 Plan，不实现 Replan。产物只在当前运行内传递，NO_RESULT 停止，不做跨计划复用。以 AGENTS.md 的最新项目原则为准。

## 1. 目标、优先级与交付边界

目标：后继 Capability 真正读取前序 Capability 产生的对象，而不只是让几个返回成功的 handler 串行执行。用户已要求可交给后续开发模型执行的文档，因此本文明确数据结构、接口调整、处理顺序和测试要求。

本任务完成单次运行、同一 Goal 版本内的引用传递、对象读取和执行前门禁。沿用既有 Domain 契约和单个 Plan 的串行执行，不构建或调用 Replan，不建设通用产物治理体系。

对于产物流转首版范围，本文取代 `2026-09-21-capability-artifact-flow.md` 中完整产物注册、权威有效性治理、祖先依赖自动搜索、Planner 双层门禁、PARTIAL_SUCCESS 自动传播、跨 Goal 重验以及来源步骤退出计划后的独立复用要求。原文保留为长期参考。

与 `2026-09-21-planner-demo-v1.md` 配合：Planner 继续不做静态输入可达性证明，本任务负责实际执行前检查。本任务明确收紧部分成功规则，并验证运行中不会重规划；这些是本次接入变化，不反向要求重做完整 Planner 方案。

交付包括最小内存对象存储和真正读写对象的合成 handler 集成测试；不包括真实洞察、圈客算法、产品适配、任务分发、API 或页面。测试中的客户与策略必须标注为虚构。不得把通过合成链路验收表述为完整经营 Demo 已交付。

## 2. 实施前基线

2026-09-21 编写本文时仅检查文件，没有运行测试：

- 执行相关组件位于 `src/application/capability/`；Planner 位于 `src/application/planner/`。
- ExecutionContext 保存 goal、current_plan、known_context 和 step_results。
- build_capability_request 将 known_context 中全部 `*_refs` 传给每项能力，没有按消费者过滤。
- execute_step 只记录结果，没有结果关联校验、产物发布和后继读取。
- Ready Step、Continuation 与 Plan 完成判断将 SUCCESS/PARTIAL_SUCCESS 都视为可继续。
- CapabilityOutput 已有 output_id、output_type、payload；不需要扩展 Domain。
- Parser 正处于首版重建，旧实现和测试在工作区有删除，Planner V1 是开发依据，不能假定已实现。

先执行 git status，检查实际文件与前置任务状态。保护已有修改，不 reset、不恢复整份旧实现、不根据历史测试数量声称当前可用。完整集成前先完成 Parser V1 和 Planner V1；不得为本任务绕过它们的公共导入和门禁。

## 3. 首版范围

必须完成：

1. Capability 的最小必需输入、可选输入、输出类型声明。
2. 本次运行独享的内存对象存储，以及初始引用和运行输出的区分。
3. 显式输出引用发布；后继只能按直接依赖或初始引用取输入。
4. Result 请求关联、输出类型和对象存在性校验。
5. 缺输入、输入歧义、对象不存在时不调用 handler。
6. 仅 SUCCESS 发布产物；PARTIAL_SUCCESS 保留结果但停止自动推进。
7. 产物仅在本次单个 Plan 内消费；NO_RESULT 停止，不生成或执行第二个计划。
8. 有实际对象读写的集成测试，验证数据内容发生传递。

明确不做：数据库、事务框架、事件总线、并行、恢复会话、动态插件、通用映射 DSL、字段级绑定、跨 Goal 复用、有效期调度、来源可信度排序、引用冲突自动消解、任意多值输入策略、Planner 输入路径分析、完整生命周期。

本次只支持每种输入类型一个对象引用。多个客户用一个 customer_set 对象承载；多个机会也可由业务能力定义机会集合对象，不能为方便在框架中隐式合并多个独立机会。

## 4. 最小数据结构与职责

新增内容全部属于 Application；不修改 Domain CapabilityRequest、CapabilityResult、PlanStep。

### 4.1 CapabilityIO

在 `src/application/capability/artifact_flow.py` 定义一个 frozen dataclass：

- required_inputs: tuple[str, ...]
- optional_inputs: tuple[str, ...]
- output_types: tuple[str, ...]

三个字段默认空元组。类型字符串非空、不含冒号、首尾无空白；各列表不重复，required 与 optional 不重叠。output_types 可与输入类型相同，不因类型相同强制顺序。

通过普通 `Mapping[str, CapabilityIO]` 注入，键为 capability_id。不得新增 Registry、基类、自动发现或从 capability_id 猜类型。元数据缺失是装配错误，不能退回“全部引用都传”。

本任务不为尚未实现的五类业务能力臆造完整输入输出契约。集成测试显式声明：洞察无必需输入、输出 opportunity；圈客需要 opportunity、输出 customer_set；策略需要 customer_set、输出 strategy。这是测试能力的契约，不是固定五步顺序。

### 4.2 StoredArtifact 与 ArtifactStore

在 `src/application/capability/artifact_store.py` 定义：

- StoredArtifact：artifact_type、artifact_id、value。前两者组成 `type:id`；value 是业务代码显式保存的 JSON 兼容字典。
- ArtifactStore：普通内存字典的封装，提供 put(artifact_type, artifact_id, value) -> str、get(ref) -> StoredArtifact、contains(ref) -> bool。

类型非空且不含冒号；ID 非空且不含冒号，拒绝首尾空白。ref 必须恰含一个分隔冒号。存入和读取 value 时做深复制，防止后继修改上游事实。无需通用 Schema 校验或数据库适配层。

同一 ref 重复 put 一律报 ARTIFACT_DUPLICATE，不做内容比较、覆盖或幂等合并。同一 ID 属于不同类型时是不同 ref，可以并存。业务 handler 应为新对象分配新 ID；模型不决定存储键的可信性。

Store 只说明对象存在，不说明可被后继使用。只有已验证初始引用和已发布输出才能进入输入解析。

handler 在返回输出之前显式 put 业务对象，再用对应类型和 ID 构造 CapabilityOutput。不能由通用执行层扫描或自动保存 CapabilityOutput.payload；payload 仍可用于展示。

失败 handler 提前放入 Store 的对象可以留到本次运行结束，但没有发布记录，后继不可发现或通过解析器获取。不尝试回滚业务写操作；本 Store 仅为内存 Demo 对象存储，不能声称提供外部事务。

### 4.3 PublishedArtifact

在 artifact_flow.py 定义最小 frozen dataclass：

- ref: str
- source_step_id: str
- source_request_id: str
- source_plan_ref: 既有 Domain PlanRef

类型和 ID 从 ref 拆分，无需重复保存；Capability、状态和限制通过 source_step_id 查 step_results。Goal 绑定来自整个 ExecutionContext，不逐产物复制。

source_plan_ref 保存本次唯一 Plan 的引用，不实现跨计划来源管理。原 Result 保留 evidence_refs、rule_result_refs、execution_meta 等已有审计信息，不能因为索引精简而删除。

## 5. ExecutionContext 和运行装配

保留 goal、current_plan、known_context 和 step_results，增加：

- artifact_store: ArtifactStore，默认工厂创建，不使用共享默认实例。
- initial_refs: tuple[str, ...]，本次运行入口规范化得到，不在运行中追加输出。
- published_artifacts: dict[str, PublishedArtifact]，按 ref 索引。

known_context 仅兼容初始引用输入和既有 Planner 输入，不再承载运行产物，也不随输出自动修改。当前 GoalRef 在 Context 初始化时绑定；后续执行检查 GoalRef 未变，变化即报 ARTIFACT_GOAL_CHANGED，要求新建运行。

采用每次运行重新装配的方式：

1. 应用创建一个新 Store，放入本次允许使用的初始对象。
2. handler 通过构造参数或闭包持有同一个 Store。
3. 创建本次的 Executor 和 BusinessAgent。
4. 调用 handle 时传入同一个 Store 和初始引用。

为 BusinessAgent 构造增加 `capability_io: Mapping[str, CapabilityIO]` 必需关键字参数；为 handle 增加 `artifact_store: ArtifactStore | None = None`。无初始对象、无读写需求的测试可由 handle 创建空 Store；需要对象读写的调用必须显式传与 handler 相同的 Store。

Store 提供 bind_goal(goal_ref) 的一次绑定检查：第一次绑定成功，后续新 handle 即使相同 GoalRef 也拒绝复用已绑定 Store；同一次运行内部不要重复绑定。本次运行不更换 Plan；重新提交必须创建全新的 Context 和 Store。不同运行不可共享 Store 或其 handler 实例，不保存到全局单例。

BusinessAgent 在 Parser 成功后、首次 Planner 前构造并验证 initial_refs，随后创建 ExecutionContext 时传入已验证数据；不需要为校验初始输入提前创建虚假 Plan。Parser 澄清分支仍先返回。

### 5.1 初始引用兼容规则

known_context 键仅允许 IO 声明中出现的输入/输出类型加 `_refs`，例如 opportunity_refs；值为 list/tuple 的非空 ID 字符串，不是完整 type:id。去重并保持原顺序，构造 type:id 后必须能在本 Store 读取。

空数组允许；非法键、非法类型和不存在对象明确报错，不静默忽略。不得接受 actor_refs 或 rule_result_refs 来伪造身份或规则裁决；本首版不支持 evidence/rule_result 作为业务输入类型。已有 Result 审计引用原样保留。

这里的类型白名单来自本次实际可执行能力的 IO 声明，不硬编码客户产品名称。初始对象必须由可信应用装配，不能将模型传出的任意字符串直接登记为初始引用。

## 6. 后继输入解析：固定算法

在 artifact_flow.py 提供普通函数 resolve_input_refs(step, context, io) -> tuple[str, ...]。io 为当前能力的 CapabilityIO。

对 required_inputs 后接 optional_inputs 中的每一种类型，依次执行：

1. 只从 step.depends_on 指向的直接依赖步骤收集该类型的 published_artifacts；来源结果必须为 SUCCESS，来源步骤必须仍在 current_plan 中。
2. 按 ref 去重。若直接依赖候选非空，就只使用这一组候选，不与初始引用混合。
3. 若直接依赖无候选，查找同类型 initial_refs。
4. 候选多于一个：INPUT_AMBIGUOUS，停止，不任选第一个，也不退回初始对象。
5. 没有候选：必需类型报 INPUT_REQUIRED，可选类型跳过。
6. 唯一候选必须仍在 Store 中且类型一致，否则 ARTIFACT_NOT_FOUND/ARTIFACT_TYPE_MISMATCH；不自动降级到其他来源。
7. 依声明顺序返回 ref 元组。

无输入声明的能力收到空 input_refs。无关输出、无依赖步骤输出、祖先步骤输出不会自动传入。需要祖先输出时，在 Plan 中显式增加对其生产步骤的直接依赖；Planner Prompt 增加这条运行语义说明即可，不实现静态补边。

required_inputs 中的不同类型是全部必需，不是替代关系。不实现 any-of。可选输入出现歧义同样停止，不能静默省略。

## 7. Step Execution：校验和发布

给 build_capability_request 和 execute_step 增加必需关键字参数 `io: CapabilityIO`，BusinessAgent 从 capability_io 按步骤能力查找并传入。保留其余参数和 Domain 返回值。

execute_step 的顺序必须为：

1. 检查当前 GoalRef、step 属于 current_plan 且未执行、依赖满足 SUCCESS；否则 STEP_NOT_READY。不得重复调用已成功 handler。
2. 使用 resolve_input_refs 构造 Request，身份仍来自可信 Goal，不从 Store 或 payload 获取。
3. 调用既有 Executor。
4. 验证返回的是 CapabilityResult，request_id 和 capability_id 与请求一致；不一致报 RESULT_IDENTITY_MISMATCH。
5. 非 SUCCESS 结果只记录，不发布任何输出，再交给继续策略处理。
6. SUCCESS：对全部 outputs 先在局部变量中校验，校验完成前不修改 step_results 或 published_artifacts。
7. 每项 output 的 ID/类型合法，类型在 io.output_types，Store 已存在对应对象；同批或既有发布中 ref 重复，以及与 initial_refs 重复，都报 ARTIFACT_DUPLICATE。
8. 一项能力一次 SUCCESS 对每种输出类型最多输出一个对象；多个同类对象应封装为业务集合，违反时 OUTPUT_CARDINALITY_INVALID。
9. 所有输出合法后，一次串行提交 step_results 和全部 PublishedArtifact，来源 PlanRef 使用本次 Request 的 plan_ref。

不要求每次 SUCCESS 都产出全部声明类型；output_types 是允许集合，不是必需集合。SUCCESS 可以无 outputs，后继缺输入时由执行前门禁停止，不能编造占位输出。

一次输出校验失败时，不记录为可信 SUCCESS、不发布其中任何一个输出。错误以应用层错误返回，并保留已有 Context；不得伪装为 handler 自己返回的 FAILED。无需另建第二套失败历史或保存未经验证的敏感原始结果。

这里的“一次提交”是串行内存状态的一致更新：先完成全部可失败校验，再更新字典。无需锁、事务管理器或承诺进程崩溃恢复。Store 中尚未发布的对象不属于可用输入。

## 8. 状态规则与错误出口

### 8.1 状态矩阵

| Result 状态 | 记录结果 | 发布产物 | 后续 |
| --- | --- | --- | --- |
| SUCCESS | 校验通过后记录 | 仅通过校验的明确 outputs | 有 Ready Step 则继续，否则按现有完成判断 |
| PARTIAL_SUCCESS | 是，保留限制/质量 | 否 | STOPPED，说明部分完成及限制 |
| NO_RESULT | 是 | 否 | STOPPED，说明无结果，不再规划 |
| NEED_INFORMATION | 是 | 否 | 沿用澄清 |
| BLOCKED | 是，保留 rule_result_refs | 否 | STOPPED，不能重规划绕过 |
| FAILED | 是，保留 errors | 否 | STOPPED，沿用既有能力失败语义 |

必须同时校准 step_resolution、continuation：只有 SUCCESS 释放依赖和参与 Plan 完成。PARTIAL_SUCCESS 不能进入 FINISH、REPLAN 或后继执行。Domain 枚举及不变量保持不变。

### 8.2 应用错误

artifact_flow.py 定义一个 ArtifactFlowError，包含 code、message 和 missing_information（既有 MissingInformation 元组，默认空）。不增加异常继承树或 Result 状态。

| code | BusinessAgent 响应 | 说明 |
| --- | --- | --- |
| INPUT_REQUIRED / INPUT_AMBIGUOUS | CLARIFICATION_REQUIRED | 不调用 handler，question 提示补充明确对象后重新提交完整请求；不承诺会话续接 |
| ARTIFACT_NOT_FOUND / ARTIFACT_TYPE_MISMATCH | FAILED | 对象装配或引用错误，使用安全提示 |
| ARTIFACT_DUPLICATE / OUTPUT_CARDINALITY_INVALID / OUTPUT_TYPE_INVALID | FAILED | 输出或存储协议错误 |
| RESULT_IDENTITY_MISMATCH / RESULT_INVALID | FAILED | 返回关联或对象类型错误 |
| ARTIFACT_CONTEXT_INVALID / ARTIFACT_GOAL_CHANGED / ARTIFACT_STORE_REUSED | FAILED | 输入上下文或运行作用域错误 |
| CAPABILITY_IO_MISSING / STEP_NOT_READY | FAILED | 装配或调用不一致 |

INPUT_REQUIRED/INPUT_AMBIGUOUS 构造 MissingInformation：field 为 `input_refs.<type>`、reason 为安全说明、impact 说明阻止当前能力、required_before_execution 为 true。

给 BusinessAgentResponse 追加带默认空元组的 missing_information 字段，以返回上述结构化缺失，不改变已有构造调用。已有 Capability NEED_INFORMATION 分支也填入该字段；Parser 自身接口保持不变。

应用门禁发生在调用前，不创建假的 CapabilityResult，不写本步 step_results，不触发 NO_RESULT Replan。错误响应保留当前 Goal、Plan、ExecutionContext；last_result 只能是之前真实结果或 None，不能伪造本次执行。

Store 的校验错误也统一通过 ArtifactFlowError 表达；若发生在 handler 内，遵守 Executor 既有异常转 FAILED 规则并停止；在应用发布/解析阶段抛出则按上表映射。不得为此重做 Executor 异常体系。

## 9. 单次运行与单次计划边界

- 一次请求只生成并执行一个 Plan；不构建 Replan、不创建 Plan V2、不执行跨计划产物复用。
- NO_RESULT 记录后返回 STOPPED，保留当前结果供展示，不调用模型生成替代路径。
- 缺信息提示后结束本次运行；部分成功、阻断或失败同样停止。
- Store、initial_refs、published_artifacts、step_results 只属于当前运行。用户重新提交时全部重新装配，不自动复制旧产物。
- GoalRef 或 Plan 引用在运行中改变均拒绝继续；Plan 引用变化使用 ARTIFACT_CONTEXT_INVALID，Goal 变化使用 ARTIFACT_GOAL_CHANGED。
- Planner V1 应已断开重规划路径；本任务验证这一点，若尚未落实则按 Planner V1 补齐最小停止分支，不建设新的执行循环。
- Planner Prompt 只增加“需要前序产物时显式直接依赖生产步骤”的说明；不设计 Replan Prompt、历史序列化、恢复策略或换版校验。
- 不因旧代码有 replan() 或 Domain 有 version 字段就要求继续维护 Demo 重规划能力。
## 10. 文件修改边界

| 文件 | 修改内容 |
| --- | --- |
| src/application/capability/artifact_store.py | 新增最小对象存储、深复制、运行绑定 |
| src/application/capability/artifact_flow.py | 新增 IO、PublishedArtifact、错误、初始引用规范化、输入解析和输出校验普通函数 |
| src/application/capability/execution_context.py | 最小运行字段和 Goal 绑定 |
| src/application/capability/step_execution.py | 输入解析、结果校验、统一发布 |
| src/application/capability/step_resolution.py | 只允许 SUCCESS 释放依赖 |
| src/application/capability/continuation.py | 部分成功停止，完成判断只认 SUCCESS |
| src/application/business_agent.py | Store/IO 注入、初始校验、应用错误映射、结构化缺失 |
| src/application/planner/planner.py | 仅补首次规划 Prompt 中直接依赖输入说明；不改造 Replan |
| src/application/planner/plan_validation.py | 保持首次 Plan 校验，不新增跨版本校验 |
| src/application/__init__.py | 必要公共导出 |
| tests/application/test_artifact_flow.py | 存储、解析、发布测试 |
| tests/application/test_artifact_flow_integration.py | 实际对象传递、无结果停止和阻断测试 |

不修改 Domain、Model、Agent Runtime、Parser 实现、Web，不引入新依赖。测试装配和合成 handler 放在测试模块，不写进生产 Catalog 作为虚假的业务能力。更新已有受影响测试和调用方，不删除测试以掩盖契约变化。

artifact_store 与 artifact_flow 若存在导入环，错误类型可移到 artifact_store 并由 artifact_flow 重导出；不为一个异常再拆包。除这个内部位置选择外，不自行扩展本文协议。

## 11. 实施顺序

1. 检查当前工作区、前置 Parser/Planner V1 及导入基线，记录已有失败。
2. 实现 Store、IO 与引用格式校验，先通过独立离线测试。
3. 扩展 Context、规范化初始引用；接入 BusinessAgent 的每次运行装配。
4. 实现直接依赖输入解析和执行前错误出口，验证不调用 handler。
5. 实现结果关联校验、SUCCESS 输出校验和统一发布。
6. 同步部分成功的 Ready/Continuation 语义，并确认 NO_RESULT 停止；不能只改一处。
7. 用实际读写 Store 的合成 handler 跑通三步链路、跳步和无结果停止，确认没有第二次计划。
8. 跑完整离线测试，校准事实文档和开发日志。此后停止，不附带建设业务规则或前端。

## 12. 验收矩阵

| 编号 | 场景 | 必须断言 |
| --- | --- | --- |
| T01 | Store put/get | 内容可读取，读写深复制；非法 ref 拒绝 |
| T02 | 重复 ref 和不同类型同 ID | 同 ref 拒绝，不覆盖；不同类型可并存 |
| T03 | 三步真实数据链 | 洞察保存 opportunity；圈客读取其中条件生成 customer_set；策略读取其客户列表生成 strategy |
| T04 | 初始引用跳步 | 应用预存机会，直接圈客成功；没有假造前序步骤 |
| T05 | 直接依赖优先 | 直接依赖与初始对象同类型时，只传直接依赖对象 |
| T06 | 缺必需输入 | CLARIFICATION_REQUIRED、结构化缺失，handler 零次，step_results 无本步，无 Replan |
| T07 | 多候选歧义 | 不选第一个、不回退；可选输入歧义也停止 |
| T08 | 无关与祖先引用 | 无关步骤/仅祖先输出不传；显式直接依赖后可传 |
| T09 | 无输入/可选输入 | 无输入收到空元组；缺可选类型可继续 |
| T10 | 请求关联错误 | request_id/capability_id 任一错误拒绝，不记录成功、不发布 |
| T11 | 输出类型或对象错误 | 未声明类型、非法 ID、Store 不存在拒绝 |
| T12 | 批次后一项非法 | 前一项也未发布，step_results 未新增；Store 暂存对象不能被消费 |
| T13 | outputs 重复与同类型多对象 | 明确拒绝，不覆盖、不隐式合并 |
| T14 | payload/审计引用 | 不合并 payload，不从 summary 猜类型；evidence/rule refs 保留但不作为普通输入 |
| T15 | 非 SUCCESS 结果 | 参数化验证无产物发布；NO_RESULT/缺信息/阻断/失败保持正确后续行为 |
| T16 | PARTIAL_SUCCESS | 结果与限制保留；STOPPED；后继不 Ready；Plan 不完成；不 Replan |
| T17 | NO_RESULT 停止 | 保留已有对象与结果但不执行后继；replan 调用零次；只有原 Plan |
| T18 | 重新提交独立运行 | 新 Store/Context 不继承旧产物，不能用旧引用继续旧计划 |
| T19 | 运行隔离/Goal 变化 | 两次运行不共享对象；复用绑定 Store 或改变 GoalRef 被拒绝 |
| T20 | 初始 Context 非法 | 非法键、裸字符串、不存在 ID 被拒绝；可信 actor/channel 不受影响 |
| T21 | 装配/重复执行 | 缺 IO、非 Ready 或重复 step 不执行 handler |
| T22 | BLOCKED 审计 | 合成规则阻断保留 rule_result_refs；后继零次，不用 Replan 绕过 |

T03 必须改变上游对象内容再验证下游输出相应变化，不能只检查三个状态都是 SUCCESS 或让下游返回固定答案。合成数据可在测试中定义，但不能把测试结论描述为真实经营算法正确。

T22 只证明执行框架尊重 BLOCKED；真实客户归属、渠道规则正确性需要后续业务测试，不在这里伪造覆盖。

从仓库根目录执行 PowerShell：

```powershell
.\.venv\Scripts\python.exe -c "import src.application; print('application import ok')"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
git diff --check
```

解释器不存在先检查已有环境，不擅自安装工具。此任务以确定性离线测试为验收，不强制真实模型调用。涉及 Planner Prompt 的修改若未在线验证，明确记录未执行；FakeModel 不能证明真实模型会正确声明直接依赖。

## 13. 完成标准与后续业务边界

- T01～T22 对应行为通过，原有 Parser/Planner 测试仍通过或针对明确的新状态边界完成必要更新。
- 无共享全局 Store、无任意 payload 合并、无失败产物传播、无部分提交的可信输出。
- current-state 更新真实流转能力、PARTIAL_SUCCESS 停止、直接依赖和同 Goal 运行限制，并注明实际验证日期。
- architecture 更新新增两个模块和对象读取/引用传递路径；dev-log 的 Unreleased 记录行为变化及测试结果。
- 不修改事实文档为“支持通用有效性治理”或“完整 Demo 已完成”。

后续真实 Capability 必须通过引用解析对象并独立检查业务适用条件；存在对象不等于有经营权限。任务创建/分发前仍必须由确定性规则阻断非当前代理人或非个险可经营客户。数据、产品知识和规则保留版本来源，内存 Store 不替代这些业务事实要求。

## 14. 可复制给开发模型的任务

> 请按 `doc/design/2026-09-21-capability-artifact-flow-demo-v1.md` 实现产物流转 Demo V1。先读取 AGENTS.md、当前事实文档、Parser/Planner V1 和本文，检查工作区并保护已有修改。确认前置公共入口可用，不恢复旧 Parser、不重做 Planner。严格按本文实现每次运行独享的内存对象存储、最小 IO 声明、直接依赖输入解析、结果关联校验、仅 SUCCESS 发布、PARTIAL_SUCCESS/NO_RESULT 停止与单次计划执行。遵守文件边界、错误映射、开发顺序及 T01～T22；必须有实际对象内容传递的集成测试。不要实施原收敛方案的跨 Goal 复用、有效期治理、Planner 双层门禁、通用注册中心或完整恢复体系。完成后同步 current-state、architecture、dev-log，报告实际测试和限制，不声称真实经营能力、API 或完整 Demo 已完成。

