# 开发日志

## [Unreleased]
- 2026-09-22 重构 `scripts/smoke_real_insight_agent.py` 为一次真实发送的两幕场景：自然语言 Goal 经 GoalParser 和唯一 Planner Plan，第一幕程序保证知识检索、指纹原文读取与快照聚合，再由模型形成并校验正式 Opportunity；第二幕经直接依赖读取 Opportunity、完整查询 50 人证据、模型评估、程序校验并发布三层名单和仅含优先客户的 `customer_set`。JSONL 逐动作记录公开业务理由、可信输入、事实/模型推断/规则结果及输出，不向模型声明评测或测试，也不输出隐藏推理。真实模型 `deepseek-v4-flash` 实际完成一次：优先 2、进一步了解 4、持续关注 4、排除 40，单 Plan、无 Replan、两幕同为 `insight_demo_v2/2.0`；该结果仍是合成数据场景，第一幕 handler 尚未下沉为可复用 Application 模块。全量离线测试 74 项及数据校验通过。


- 2026-09-22 发布共享合成快照 `insight_demo_v2/2.0`：保留 50 位客户并将行为补充至 117 条（主窗口/历史 107/10），覆盖明确自身需求、一般咨询、替他人询问、同主题撤回和无关主题否定；主题、素材、产品目录与 manifest 统一版本并重算实际指纹，v1 身份与旧指纹保存在 `data/client/versions/1.0-manifest.json`。独立人工标注保存在运行时不可读的 `data/evaluation/`。

- 2026-09-22 新增 `query_customer_evidence`、`assess_customer_opportunity` 与可装配的 `customer_targeting` handler/IO。查询 Tool 绑定可信 actor/channel/快照并保留完整近期、稀疏历史、负向及跨主题上下文；模型 Tool 只解析受信引用，复用现有 ChatModel，输出显式模型推断与审计元数据。Capability 校验引用、逐字片段、客户归属、版本、时间、受控主题和层级一致性，发布三层展示结果，但下游 `customer_set` 只含优先沟通客户；不实现产品匹配、策略、任务、预测、Replan、API 或前端。

- 2026-09-22 数据校验通过：50 位客户、117 条行为、107/10 主窗口/历史事件、40 位近期活跃客户及 7 项数据变体。完整离线测试 74 项通过并完成 `src`、`tests`、`scripts` 编译与 `import src.application`；新增圈客测试覆盖模型错误/非法输出、伪造和跨客户引用、一般咨询强塞优先、同主题撤回、无关主题否定和优先集合交接。独立真实模型 `deepseek-v4-flash` 语义评测 7/7 标注通过；该小样本结果不代表生产泛化、产品适配或完整链路验证。

- 2026-09-22 实现 `src/application/insight_tools.py` 的三个通用只读 Tool：`search_knowledge` 按产品目录正式名/已登记别名检索 Markdown 章节，`read_knowledge` 按文档指纹读取精确原文行区间，`aggregate_records` 在 `customer_profiles`/`customer_behaviors` 上执行白名单字段、时间窗、同事件筛选、分组和独立客户统计。复用 `src/agent/tool.py` 的 `Tool`/JSON Schema 校验，来源保留 dataset/version/manifest 或文档指纹；拒绝路径、SQL、代码和任意字段，不生成机会、推荐、名单或预测。新增 5 项离线测试覆盖别名、原文版本、非法参数、分母/去重/同事件语义及源数据变体；本轮未接入洞察 Capability、Planner、Replan、API 或前端，也未声称完整 M4 完成。

- 2026-09-22 新增 `scripts/smoke_real_insight_agent.py`：复用既有 `OpenAIChatModel`、`AgentLoop` 和三个只读洞察 Tool，要求真实模型按当前故事线检索产品资料、读取带指纹原文、计算 90 天行为/明确表达统计，并输出带限制的待核实经营方向。脚本确定性检查工具覆盖、实际 105/40/15 统计和禁止的推荐/适配/收益/NBEV 预测结论；本轮未执行在线模型验证。

- 2026-09-22 根据一次真实模型输出修正冒烟断言：否定性限制语句（如“不能预测 NBEV”“不等于推荐购买”）不再误判为正向业务结论；新增离线覆盖正向预测/推荐与限制性表述两类断言。

- 2026-09-22 交付 M4 数据快照至 `data/client/` 与 `data/product/`：按已确认设计生成 50 位虚构个险客户和 115 条行为，附主题/素材字典、仅索引用户提供 Markdown 原文的产品目录、manifest、README 及标准库校验脚本。校验从实际文件计算统计和 SHA-256，验证年龄置换、行为配额、主窗口/历史分区、引用、statement_kind 文本一致性、渠道/代理人范围、去重口径和 7 项独立反例；本轮未开发 Capability、Tool、API、前端或 Replan，也未声称 M4 洞察能力已实现。

- 2026-09-22 扩展 `scripts/smoke_demo_v1.py` 的可观察性：默认输出带 case、sequence 和 event 的 UTF-8 JSONL 全流程日志，覆盖可信运行上下文、初始产物、Parser/Planner 模型请求与响应、结构化 Goal/Plan、每个 CapabilityRequest/Result、实际 ArtifactStore 读写、确定性渠道/归属规则裁决、发布索引和最终模拟任务；不打印密钥、SDK 配置或隐藏推理。重新执行两个合成样例均完成，完整目标共 28 个事件，已知客户目标共 21 个事件，中文输出正常。

- 2026-09-21 完成三份 Demo V1 开发文档定义的首版实现。Goal Parser 改为单次严格 JSON 提取，可信 actor/channel 只来自 RuntimeContext，受治理指标当前仅含 NBEV，金额执行有限确定性规范化；缺信息、协议失败、原文依据失败和模型失败均在 Planner 前停止，已有 Goal 修改与澄清续接延后。
- Planner 新增 `PlanningUnavailableError`/`PlannerError`、严格成功/无法规划协议、受控 `*_refs` Context 和 Catalog/callable handler 交集；只有 JSON 语法错误允许一次格式修复。Demo 执行入口及 Planner 已移除 Replan/Plan V2 路径，NO_RESULT、PARTIAL_SUCCESS、BLOCKED 和 FAILED 均保留结果后停止，只有 SUCCESS 释放依赖。
- 新增单次运行 ArtifactStore、CapabilityIO、PublishedArtifact、初始引用规范化、直接依赖输入选择、结果关联检查和 SUCCESS 原子发布。合成三步集成测试实际读取上游对象并验证上游内容变化会改变下游策略；缺输入、歧义、非法输出、重复执行和运行复用在 handler 或后继执行前被阻止。
- 新增 `scripts/smoke_demo_v1.py`，以明确标识的虚构客户、机会、策略和规则跑通两个端到端样例：完整开门红目标形成四步 Plan V1 和个险模拟任务；“王女士下一步应该怎么经营”通过可信初始 customer_set 跳过洞察/圈客，形成两步 Plan V1 和模拟任务。两例均记录 `execution_mode=simulated`，不代表真实经营能力完成。
- 2026-09-21 实际验证：公共 `src.application` 导入通过；完整离线 `unittest` 62 项通过；`src`、`tests`、`scripts` 编译通过；两个合成端到端冒烟通过。真实模型配置存在，但沙箱内在线调用均返回 `MODEL_CALL_FAILED`，外部端点访问未获授权，因此未完成在线模型验证；未把 FakeModel 或合成 handler 结果表述为真实模型/真实经营能力验证。

- 2026-09-21 用户确认收缩 Demo 范围：仅交付一次 Goal 分析、Opportunity 发现、圈客和策略执行；每次请求最多一个 Plan，不构建或接入 Replan。NO_RESULT 停止，缺信息提示后结束运行，部分成功、阻断或失败不生成替代计划；追踪反馈、剩余目标调整和跨计划复用延后。已同步 AGENTS.md、开发基线、Demo 故事及相关首版设计/开发文档，将重规划验收改为禁止调用重规划。策略执行前确定性业务校验保留。本次只修改文档，未修改代码或执行运行测试；现有代码中的 Replan 路径尚未因此被禁用。此前同日“最多一次 Replan”的首版决策由本条范围决定取代。

- 2026-09-21 完成 Goal Parser 收敛最小实现：在 `src.application.goal_parser` 保持统一入口，新增版本化 NBEV 指标词汇快照、顶层 `KEEP/SET/CLEAR` 合并、首次 `original_request` 保留、阻塞性 `MissingInformation`、单次 JSON 格式修复及明确技术失败结果。BusinessAgent 读取解析状态，在阻塞澄清时不调用 Planner；actor/channel 仍只由 Runtime Context 注入。新增 Goal Parser 契约测试，覆盖创建、可信上下文、指标白名单、澄清不规划、修改/清空、旧版本不可变、原文过滤和单次修复。2026-09-21 当前 19 项 `unittest` 与 `src`、`tests` 字节码编译通过；未执行真实模型在线验证。

- 2026-09-21 确认 `doc/design/2026-09-21-replan-convergence.md`：Replan 复用 Planner，以结构化 Trigger、受控 Snapshot、完整 Plan 新版本和原子切换收敛跨版本恢复；Demo 首版仅自动处理 `NO_RESULT`，由显式运行 Policy 管理一次预算。确认有效成功产物与步骤分离、失败步骤退出新活动依赖链、失败模型生成尝试消耗预算，以及通过版本链和审计事件推导旧 Plan 的 `SUPERSEDED`。该结论不改变当前代码、实现事实或验证基线。

- 2026-09-21 确认 `doc/design/2026-09-21-capability-artifact-flow.md`：Application 使用产物注册表分离初始产物、运行产物和执行历史；只发布受控的显式输出，禁止 payload 自动合并；Capability 采用最小输入输出类型边界，后继输入按依赖与初始 Context 受控解析。确认 Planner 与执行前共用输入不足双层门禁，首版以权威来源有效性、Goal 关联和保守冲突拒绝控制产物复用。该结论不改变当前代码、实现事实或验证基线。

- 2026-09-21 确认 `doc/design/2026-09-21-planner-convergence.md`：首次规划采用模型草案与正式 Plan 分离、Application 分配正式 step ID、统一规划结果、受控 Planning Context 和 Application Capability View；明确首版可执行性校验边界、一次可观察的受限语义重试、无需行动不创建空 Plan、生命周期由 Application 执行协调职责管理，以及先等价拆分 Planner 内部结构再引入行为变化。本次仅确认设计，未修改代码、当前实现事实或验证基线。

- 2026-09-21 将 `doc/roadmap/M1/` 的领域边界、Goal、Evidence、Opportunity、Capability、状态、Plan 和契约测试设计收敛到唯一整体文档 `M1.md`；删除已被合并且包含旧字段方案的 T01～T08 分篇，避免与当前代码和收敛决策形成双重事实源。整体文档新增“未来可新增的契约细节”和演进评审清单，分别说明非量化完成条件、证据冲突、圈客条件、机会有效性、写操作策略、类型化 Capability 输入、持久运行状态及新领域产物的真实触发条件和归属边界。本次仅调整文档，未修改代码行为或验证基线。
- 2026-09-21 按已确认的近期消费边界收敛 Domain Contract：Goal 删除与量化 Target 重复且当前无消费者的 `success_criteria`；Evidence 删除开放式 `payload` 和混合质量对象，改为最小 `subject_ref/field/value`、观测/有效时间及可选置信度和限制；Opportunity 复用 `GoalRef`，删除目标贡献、适用条件、圈客逻辑、有效性和下一步提示等后续阶段字段，优先级收敛为可选值与必配理由。
- CapabilityRequest 删除宽泛 `CapabilityContext` 和未消费的请求约束，显式保留 actor、对象范围、统一 `input_refs` 与 `as_of`；Application 只把 `known_context` 中 `*_refs` 字符串引用映射入请求，不再透传任意属性。PlanStep 删除未使用的运行状态、上下文引用和模型控制点，只保留 capability 选择与依赖；写操作控制继续作为后续 Capability 元数据/执行策略职责。
- 同步领域和单步执行测试，新增 Evidence 置信度、轻量 Opportunity 优先级解释及引用式 CapabilityRequest 覆盖；2026-09-21 完整离线测试 76 项通过，并完成 `src`、`tests`、`scripts` 字节码编译。本轮未执行真实模型在线验证。

- 2026-09-20 完成 M3-T07 最小执行闭环：BusinessAgent 在 Goal Parser 与 Planner 之后创建 ExecutionContext，直接组合 Ready Step 解析、CapabilityExecutor、单步执行、Continuation Policy 和 `Planner.replan()`；成功自动推进，`NO_RESULT` 最多触发一次 Plan 新版本，`NEED_INFORMATION` 返回澄清，`BLOCKED/FAILED` CapabilityResult 返回停止。响应保留最终 Plan、ExecutionContext 和最近结果；未新增 ExecutionEngine、Retry、Fallback、Resume、并行调度或持久化。
- 新增 5 项 BusinessAgent 执行行为测试，覆盖正常三步且不重规划、`NO_RESULT → Plan V2` 且成功步骤不重跑、缺信息询问、规则阻断停止和技术失败不重试；既有 8 项动态规划行为测试接入 Fake Capability 后继续验证单能力和已有上下文跳步。完整离线测试共 74 项通过，并完成 `src`、`tests` 及 BusinessAgent 冒烟脚本字节码编译；真实模型 Replan 本轮未执行。

- 2026-09-20 完成 M3-T06 最小 Replan：在既有 `Planner` 上增加只处理 `NO_RESULT` 的 `replan()`，向同一 ChatModel 提供 Goal、当前 Plan、已知 Context、历史步骤结果、最近结果和 Capability Catalog，并通过既有 `Plan.revise()` 生成同一 plan_id 的完整下一版本；未新增 Replanner/Engine、PlanPatch、Retry、Fallback、候选 Plan 比较、重规划历史仓库或生产执行循环。
- 新增 `validate_replan()`，仅阻止已取得 `SUCCESS/PARTIAL_SUCCESS` 的旧 step_id 在新 Plan 中改变 capability_id；重规划仍复用 `validate_plan()` 的 Catalog、唯一 ID、依赖存在和无环校验。新增 6 项 FakeModel 测试，覆盖 Plan V2、成功步骤不重跑、同 Capability 新 step_id 再执行、Catalog 外能力拒绝、成功步骤身份保护，以及 `NO_RESULT → REPLAN → Plan V2 → FINISH` 最小闭环；完整离线测试共 69 项通过，并完成 `src`、`tests` 字节码编译。

- 2026-09-20 完成 M3-T05 最小 Continuation Policy：新增 `ContinuationAction`、`is_plan_finished()` 与 `decide_continuation()`；成功类结果根据 Ready Step 和完成状态进入 `CONTINUE/FINISH`，`NO_RESULT` 进入 `REPLAN`，缺信息进入 `ASK_USER`，业务阻断、技术失败及不一致状态进入 `STOP`。`REPLAN` 仅作为 T06 接入点，未新增 Policy 类、Retry、Fallback、Resume、重规划实现或执行循环。
- 新增 8 项单元测试，覆盖成功继续、成功完成、部分成功继续、无结果重规划、缺信息询问、业务阻断停止、技术失败停止和无 Ready Step 且未完成时停止；完整离线测试共 63 项通过，并完成 `src`、`tests` 字节码编译。
- 2026-09-20 完成 M3-T04 最小 Ready Step 解析：新增普通 `is_step_ready()` 与 `get_next_ready_step()`；仅当步骤未执行且全部依赖结果为 `SUCCESS` 或 `PARTIAL_SUCCESS` 时 Ready，并按 Plan 出现顺序选择第一个 Ready Step。未新增调度器、优先队列、并行执行、第二套 Step 状态、Plan 完成/卡住判定或 Continuation Policy。
- 新增 6 项单元测试，覆盖无依赖步骤、已执行步骤、依赖未完成、成功与部分成功释放依赖、非成功状态阻断、多个 Ready Step 的 Plan 顺序选择，以及三步依赖链各执行一次的最小端到端链路；完整离线测试共 55 项通过，并完成 `src`、`tests` 字节码编译。
- 2026-09-20 完成 M3-T03 最小单步执行链路：新增普通 `build_capability_request()`，把 PlanStep、当前 Goal/Plan 版本、可信 actor/channel 来源和已知上下文映射为 M1 既有 CapabilityRequest；新增 `execute_step()`，经 CapabilityExecutor 执行并将成功或失败结果写入 ExecutionContext。未新增 Builder、Factory、调度器、状态机、Ready 判断、输出合并或执行循环。
- 新增 3 项单元测试，覆盖请求字段映射、成功分发并记录和 Executor 失败记录；完整离线测试共 49 项通过，并完成 `src`、`tests` 字节码编译。
- 2026-09-20 完成 M3-T02 最小 ExecutionContext：仅保存当前 Goal、当前 Plan、已知事实和按 step_id 索引的 CapabilityResult；`record_result()` 覆盖同一步骤的最新结果，不自动合并 Capability 输出，未新增执行状态、Plan 历史、产物解析或步骤调度。
- 新增 3 项 ExecutionContext 单元测试，覆盖默认容器隔离、已知事实与执行结果分离，以及同一步骤结果替换；完整离线测试共 46 项通过。
- 2026-09-20 完成 M3-T01 最小 CapabilityExecutor：以普通 `capability_id -> callable` 映射执行已有 CapabilityRequest，成功结果原样返回，未注册 handler 与 handler 异常分别收敛为 M1 既有的依赖类和内部类 `FAILED` CapabilityResult；Capability Catalog 与执行映射保持分离，未新增 BaseCapability、Registry、生命周期、重试、执行上下文或步骤调度。
- 新增 3 项 CapabilityExecutor 单元测试，覆盖成功分发、handler 缺失和 handler 异常；完整离线测试共 43 项通过。

- 2026-09-20 新增 `scripts/smoke_bussiness_agent.py`，使用配置的真实 LLM 服务验证 BusinessAgent 完整链路，覆盖仅看机会、已有 Opportunity 直接圈客和模糊指标澄清三个场景，并检查澄清时不进入 Planner；脚本仅使用虚构标识和测试输入，并打印每次模型 JSON 与最终结构化响应。在线验证先后暴露“刚才的机会”误澄清，以及模型为泛化“测试业绩”创造指标代码并跳过澄清的问题；前者通过 Prompt 规则修正，后者增加确定性澄清门禁，完整离线测试增至 40 项。脚本已调整为逐调用打印进度，并限定 30 秒超时、零重试；修复后的最近一次在线复验在第一个模型调用处明确返回 `Model request timed out`，未进入后续业务链路。
- 2026-09-20 完成 M2-Lite Step 5 和 Step 6：新增轻量 `BusinessAgent`，串联 Goal Parser、澄清分支、Planner 与 Plan Validation，对外提供 `PLAN_READY`、`CLARIFICATION_REQUIRED`、`FAILED` 三种结果；未新增 Agent Loop、Workflow Engine、状态机或 Capability 执行。
- 新增 8 个核心 Demo 行为场景，覆盖仅看机会、已有 Opportunity 直接圈客、已有 Customer 直接生成策略、任务追踪、复杂绩效目标、模糊指标澄清、非 Demo 产品和非开门红场景；另验证规划失败收敛为 `FAILED`。完整离线测试共 38 项通过，并完成 `src`、`tests` 及冒烟脚本字节码编译；本轮未重新执行真实模型在线验证。
- 2026-09-20 完成 M2-Lite Step 4：新增独立 `validate_plan(plan, capability_catalog)`，仅确定性检查 Catalog 外能力、重复 step_id、未知依赖和依赖环，并由 Planner 在返回 Plan 前调用；未引入错误层级、PlanDraft、上下文依赖求解或语义修复。
- 新增 4 项独立 Plan Validation 测试，分别覆盖上述四类非法 Plan；连同既有测试共 29 项通过。
- 2026-09-20 完成 M2-Lite Step 3：新增直接依赖 `ChatModel` 的 `Planner`，以 Goal、简单 Existing Context 和 Capability Catalog 生成 M1 `Plan/PlanStep`。Prompt 明确要求最少合理能力、无固定顺序、复用已有 Context 且不得创造 Catalog 外能力；Plan 身份、版本、GoalRef 和状态由 Application 构造，非法 JSON 最多进行一次纯格式修复。
- 新增 6 项 Planner 单元测试，覆盖只看机会、已有 Opportunity 直接圈客、已有 Customer 直接生成策略、任务追踪、Catalog 外能力拒绝和 JSON 格式修复；新增 `scripts/smoke_planner.py`，使用虚构 Goal 与引用调用真实模型，四个动态选择场景均只选择所需单一能力。完整离线测试共 25 项通过；独立轻量 `validate_plan()` 留待 Step 4。
- 2026-09-20 完成 M2-Lite Step 2：新增基于 `ChatModel` 的 `GoalParser`、最小 `RuntimeContext` 和 `GoalParseResult`，支持自然语言构造新 Goal、已有 Goal 的基础 SET 修改以及模糊指标澄清。业务语义来自模型；Goal ID、版本、原始请求和可信 actor/channel 由 Application 管理。
- Goal Parser 不向模型提供 RuntimeContext，并确定性忽略模型生成的活动日期及未在用户原文出现的产品/需求提及；新增示例 NBEV 目标、可信上下文覆盖、模糊“业绩”澄清、50 岁不推导养老需求和 Goal 修改测试。连同既有测试共 19 项通过，并完成 `src` 与 `tests` 字节码编译。
- 新增 `scripts/smoke_goal_parser.py`，使用明确虚构的数据调用配置的真实模型，打印用户问题、模型 JSON 与 Python 处理结果，并对绩效目标、模糊指标澄清和年龄不得推导需求进行断言。在线验证发现模型可能返回非标准 `target_type`，Parser 已调整为优先按 JSON 值类型识别数值；最终三个场景均通过。
- 2026-09-20 完成 M2-Lite Step 1：新增轻量 `src/application/` 与 `CAPABILITY_CATALOG`，声明定向洞察、自动圈客、策略生成、校验分发、追踪迭代五类独立经营能力；Catalog 不包含固定顺序、步骤编号或前后继关系，且未提前实现 Goal Parser、Planner、Capability 执行、版本解析或可用性注册。
- 新增 Capability Catalog 自动测试，锁定五项能力 ID 与描述并检查不存在固定 Workflow 元数据；连同 M1 领域契约共执行 15 项测试通过，并完成 `src` 与 `tests` 字节码编译。
- 2026-09-17 完成 M1 Domain Contract：新增独立 `src/domain/`，定义版本化 Goal、可追溯 Evidence、Evidence 驱动 Opportunity、统一 Capability Request/Result 状态以及轻量 Plan 依赖校验；未向通用 Agent/Model Runtime 加入业务语义，也未实现 Parser、Planner、Capability 执行或业务数据接入。
- 新增标准库 `unittest` 领域契约测试，覆盖 Goal 版本、证据类型和来源、Opportunity 证据角色、Capability 状态不变量，以及部分/重复/并行 Plan 和非法依赖；验证命令及结果见当前实现状态的测试入口。

- 2026-09-16 扩大桌面对话内容区：主栏最大宽度由 860px 调整为 1180px，智能体过程卡片与最终 Markdown 回答使用完整主栏宽度；移动端布局和输入框宽度保持不变。
- 2026-09-16 按已确认的对话页面设计重构前端：初始页以“智慧经营智能体”和居中输入框为主体，进入对话后用户消息靠右、智能体内容靠左；移除顶部 Logo、连接说明及所有面向用户的 Turn 文案。中间模型公开说明保持可见，每次 Tool 调用默认折叠且可在执行中查看输入，最终文本使用 Markdown/GFM 渲染；同时补充中文输入法防误发、非正常流结束识别、停止时工具状态收敛和用户上滚后的“回到最新”行为。
- 新增 `react-markdown` 与 `remark-gfm` 作为轻量正文渲染依赖。前端 TypeScript 检查及 Vite 生产构建通过；使用真实模型流在浏览器验证三段公开说明、五次 Tool 调用、Markdown 标题/表格/列表、折叠详情和运行结束，并检查桌面与 390×844 移动视口。构建输出写入临时目录，未覆盖已有 `web/dist`。
- 2026-09-16 扩展 Agent SSE 可观察性：Tool 事件返回所属 Turn、输入参数和结构化结果，文本增量携带 Turn；前端按 Turn 分组模型公开的中间说明，并为每次 Tool 调用提供默认展开、可折叠的输入与结果视图。同时修复轨迹后正文被 CSS 网格放入角色窄栏导致逐词换行的问题。
- 2026-09-16 将专用 `ActsOneToThreeAgent` 重构为通用 `ManageAgent`：每次请求创建独立 Trace，模型在多个 Turn 中自主选择 Tool、观察结果并决定下一步；移除应用层必经产物检查、固定机会选择和确定性模板补跑。
- 将模型可见能力归入 `src/manage/tools/`，按非私有模块自动发现 `create_tool(context)`；现有四个 Tool 均可独立调用，不再通过会话标志强制固定顺序。提示词归入 `src/manage/prompts/`，不再包含固定幕次和工具路径。
- 将 `ScenarioRepository` 替换为面向版本化事实的 `BusinessDataRepository`，对外 Tool 和 HTTP 契约统一使用 `data_source_id`；现有 CSV 的 `scenario_id` 仅作为历史数据格式保留。
- 新增 FastAPI `POST /api/chat/stream`，把真实 Agent 的 Trace、Turn、Tool、文本与终止状态映射为 SSE；新增 HTTP 契约测试。
- React 前端移除固定三幕状态和内置答案流，默认连接真实后端，并根据实际 Tool 事件动态渲染任意数量的执行步骤。
- 2026-09-16 共执行 12 项数据、业务、Tool 自动发现、Agent 自主性、事件和 HTTP 测试通过，并通过 Python 编译与已有数据重算校验。前端 TypeScript 检查和使用全新临时输出目录的 Vite 生产构建通过；现有 `web/dist` 因文件权限未覆盖。
- 新增 `web/` Node.js + React 前端：以单一对话工作区呈现前三幕，支持三幕执行进度、逐字流式输出、停止生成、键盘发送、响应式布局和减少动态效果偏好。
- 新增可替换的流式接口适配层，支持 SSE/NDJSON 事件；未配置后端地址时使用与当前 86→41→12 场景一致的内置合成演示流，并明确保留演示数据标识。
- 2026-09-15 完成前端 TypeScript 检查与 Vite 生产构建；本地开发服务返回 HTTP 200。因本机内置浏览器连接不可用，未完成截图级视觉验证。
- 新增 `src/manage/` 前三幕业务包：场景 Repository、结构化结果契约、确定性机会分析与圈客服务、四个业务 Tool、提示词和 Agent 用例入口。
- 新增三类机会的透明指标与综合排序，规则快照保存规模、需求、响应、置信度、风险和相对成本权重；当前综合分稳定推荐“家庭责任变化与重疾保障缺口”。
- 将优先级评分中原先硬编码的缺口分值、近期窗口和浏览上限补充到版本化规则快照；生成器校验改为复用正式业务实现并验证推荐机会。
- 新增客户级硬规则结果、评分贡献、证据引用、允许动作和禁止动作；C001、C028 的结果均由正式业务服务重算。
- 新增 Agent 必经产物检查和确定性模板降级；模型失败、漏调 Tool 或无最终文本时仍返回可验证业务结果并标记原因。
- 新增 9 项业务服务、Tool、Agent 闭环和回答事实一致性测试；2026-09-15 共执行 11 项测试通过，并通过数据校验、Python 字节码编译和本地入口检查；本轮未执行真实模型冒烟。
- 新增前三幕合成数据生成器，以 CSV 保存场景、经营请求、客户、保障、授权、行为、触达、敏感状态、适当性、机会定义和计算规则。
- 新增隔离的场景测试期望和确定性校验，能够从原始事实重算 86→41→12 漏斗、14/9/7/6/9 排除分布以及 C001、C028 的高优先级结果。
- 新增数据测试，验证仓库场景结果和逐字节可重复生成；2026-09-15 执行 2 项测试通过，并通过 Python 字节码编译。
- 新增 `scripts/smoke_agent_loop.py`，离线验证 Agent Loop 的模型工具调用、工具结果回传、最终回答和 Trace 终止状态，并实时打印结构化运行日志。
- 修正 Agent Loop 对当前 `model` 包的导入，避免运行时引用不存在的包名。
