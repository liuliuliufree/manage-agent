# 当前实现状态

## 当前能力

- `src/model/` 提供 `ChatModel` 契约、OpenAI-compatible 配置与实现、FakeChatModel 和模型错误类型。
- `src/agent/` 提供 Tool 定义、Trace/Turn/ToolExecution 状态、生命周期事件和通用多轮 Agent Loop；该 Runtime 不感知智慧经营业务概念。
- `src/domain/` 提供不依赖 Agent/Model 的 Goal、Evidence、Opportunity、Capability 请求/结果与轻量 Plan 契约。本轮未修改 Domain。
- `src/application/goal_parser/` 已实现 Goal Parser Demo V1：每个正常请求只调用一次模型，按严格 JSON 协议提取单一完整目标；可信 actor/channel 只来自 `RuntimeContext`；指标由包内版本化词汇解析，当前仅配置 NBEV；正向金额支持阿拉伯数字及元、万/W、亿单位并统一保存为元。
- Parser 支持量化业绩目标和探索经营机会两类入口。阻塞缺失返回结构化 `MissingInformation` 并终止本次运行；模型调用、协议、原文依据和指标配置失败返回稳定技术错误。首版不支持已有 Goal 修订、澄清续接、自动 JSON 修复、日期计算、多指标或多目标。
- `src/application/planner/` 已实现 Planner Demo V1：输入 Goal、简单 `*_refs` Context 与当前可执行 Catalog，模型可跳过、重复和重排能力；Application 控制 Plan 身份、GoalRef、版本和 ACTIVE 状态。Planner 严格区分无法规划与技术失败，仅 JSON 语法错误允许一次格式修复。
- BusinessAgent 只把同时存在 Catalog 描述和 callable handler 的能力发送给 Planner；空交集或有效 `unable_to_plan` 停止且不执行 handler。每次运行只创建并执行一个 Plan。
- `src/application/capability/` 已实现本次运行独享的 ArtifactStore、CapabilityIO、初始引用规范化、直接依赖输入解析、结果关联校验和 SUCCESS 产物发布。Store 对对象读写做深复制；后继能力读取 Store 中的实际对象，不从 payload 或 summary 猜输入。
- 只有 SUCCESS 会发布产物并释放依赖。PARTIAL_SUCCESS、NO_RESULT、BLOCKED 和 FAILED 保留真实结果后停止；NEED_INFORMATION 或执行前缺输入返回结构化澄清。缺输入、歧义、对象不存在、输出协议错误和重复执行不会调用或继续下游 handler。
- Demo 执行入口不再包含 `Planner.replan()`、Plan V2、重规划计数或换版分支；Planner 也不再公开 Replan 方法。用户重新提交完整请求时必须创建新 Goal/Plan/ExecutionContext/ArtifactStore。
- `scripts/smoke_demo_v1.py` 提供两个离线端到端合成冒烟：完整开门红目标走洞察、圈客、策略、确定性门禁和模拟任务；已知“王女士（虚构）”通过可信初始 customer_set 跳过前置能力，直接生成策略并形成模拟任务。脚本默认按顺序输出 UTF-8 JSONL 全流程日志，包括 Parser/Planner 模型输入输出、Goal/Plan、Capability 请求与结果、对象读写、规则裁决、发布索引和最终模拟任务；不输出密钥或隐藏推理。所有经营对象、规则和 handler 均明确为合成数据。
- `data/client/` 与 `data/product/` 的活跃共享快照为 `insight_demo_v2/2.0`：保留 50 位客户，包含 117 条行为、主题/素材字典和产品原文索引；v1 身份与旧指纹归档在 `data/client/versions/1.0-manifest.json`。校验脚本从实际文件核对跨文件版本、指纹、引用、时间窗、统计与关键语义样本。
- `src/application/insight_tools.py` 提供三个洞察只读 Tool，并强制 manifest、主题、素材与产品目录绑定同一快照身份；仍不生成 Opportunity、推荐、预测 NBEV 或客户名单。
- `src/application/customer_selection.py` 提供 `query_customer_evidence` 与 `assess_customer_opportunity`：前者按可信 actor/channel/数据版本读取完整授权客户证据并区分近期与稀疏历史，后者解析受信 Opportunity/客户证据引用后调用现有 `ChatModel`，返回标记为模型推断的关联、需求状态、证据、三层建议、理由和待核实项；模型输入移除 `statement_kind`。
- 同模块导出 `make_customer_targeting_handler` 与 `CUSTOMER_TARGETING_IO`，可装配到现有 Catalog/CapabilityExecutor。handler 校验结构、引用归属、逐字片段、快照/Goal/actor/channel、受控主题和同主题后续否定，成功发布 `selection_result` 与只含优先沟通客户的 `customer_set`；确定性检查不声明证明语义正确。
- `scripts/smoke_real_insight_agent.py` 以真实自然语言 Goal 运行 GoalParser、唯一 Planner Plan、第一幕受控洞察 handler、正式 Opportunity、第二幕圈客 Capability 与 ArtifactStore 发布；JSONL 按动作记录公开业务理由、可信输入、事实/推断/规则属性和结果，不记录隐藏推理。该第一幕 handler 仍只位于场景入口，尚未成为可复用 Application 模块。`scripts/evaluate_customer_selection_model.py` 是隔离人工标注的圈客语义评测入口。
- `web/` 仍保留旧 React/Vite 对话界面代码，但仓库没有对应的当前业务 HTTP API；前端不属于本轮交付。

## 核心契约与边界

- 依赖方向保持 Application → Domain/Model；Domain、Agent Runtime 和 Model 不反向依赖业务 Application。
- Goal Parser 公共入口导出 `GoalParser`、`GoalParseResult`、`GoalParseStatus`、`RuntimeContext` 和 `MetricVocabulary`。结果状态仅为 `SUCCESS`、`CLARIFICATION_REQUIRED`、`TECHNICAL_FAILURE`。
- `existing_goal` 只保留调用兼容性：非空时不调用模型、不修订旧 Goal，提示用户重新提交完整目标。重新提交属于独立运行。
- Planner 正常返回既有 Domain `Plan`；`PlanningUnavailableError` 表示当前能力无法形成计划，`PlannerError` 表示模型、协议、Context 或 Plan 校验失败。模型只生成 step_id、capability_id 和 depends_on。
- Planner Context 只接受非空 `_refs` 键和 list/tuple 字符串引用；它只表示应用提供的引用，不证明对象存在、有效或有权限。执行阶段由 ArtifactStore 与门禁解析真实对象。
- CapabilityIO 显式声明必需输入、可选输入和允许输出类型。每种输入类型首版只允许一个对象；多个客户应封装为单个 customer_set，不做框架级隐式合并。
- 后继输入只从直接依赖步骤已发布的 SUCCESS 产物或本次运行的初始引用中选择；直接依赖产物优先，不自动搜索祖先、无关步骤或跨运行产物。
- handler 必须先显式将 JSON 兼容业务对象放入同一个 Store，再通过 CapabilityOutput 发布引用。通用执行层不扫描或自动保存 payload。
- SUCCESS 输出在全部校验通过后统一写入 step_results 与 published_artifacts；失败校验不会发布部分可信产物。非 SUCCESS 结果从不发布产物。
- 当前的确定性门禁是通用执行框架能力；真实客户归属、个险可经营范围、产品知识、规则版本和任务分发仍需后续真实 Capability/Tool 提供。对象存在不等于有经营权限。

## 已知限制

- 场景入口已由 `directional_insight` handler 正式发布绑定 Goal 与 v2 指纹的 Opportunity，并通过直接依赖交给圈客；但该 handler 尚未下沉为可复用 Application 能力，数据仍是合成快照，也没有策略、真实客户归属/权限服务或任务分发，因此不代表生产业务链完成。圈客模型语义评测规模仅 7 个独立标注样本。
- 当前没有 HTTP API、运行持久化、认证、会话恢复、并行调度、外部事务或跨 Goal/跨 Plan 产物复用。
- Parser 受治理指标词汇当前仅包含 NBEV；产品名称只作为用户原文保存，不验证真实在售或适配性。金额解析不支持中文数字、区间、算式、负数、零或 at_most 等比较意图。
- Planner 不在规划期证明全部输入可达；缺输入由执行前门禁确定性阻止。模型是否能在真实输入下稳定选择最少合理能力仍需在线评测。
- 本轮真实模型圈客语义评测已完成 7 个独立样本；另实际运行两幕场景一次并完成，产生优先 2、进一步了解 4、持续关注 4、排除 40。两者均基于合成退休收入数据，不能替代扩大标注集、重复运行、生产模型治理或真实客户验证。
- `web/` 尚未接入当前 Application 契约，本轮未验证前端构建。

## 最近验证基线

- 2026-09-21：`import src.application` 通过。
- 2026-09-21：完整离线 `unittest` 共 62 项通过，覆盖 Domain、Parser、Planner、BusinessAgent 门禁、Catalog/handler 交集、单 Plan 停止语义、ArtifactStore、实际对象内容传递、运行隔离和规则阻断保留。
- 2026-09-21：`src`、`tests`、`scripts` 字节码编译通过。
- 2026-09-22：`scripts/smoke_demo_v1.py` 两个端到端合成样例均完成，均只生成 Plan V1，并输出可读取中文的结构化全流程日志及 `execution_mode=simulated` 的个险模拟任务。
- 2026-09-22：共享 v2 合成快照校验通过：50 位客户、117 条行为，主窗口/历史事件 107/10，近期活跃客户 40，7 项独立数据变体及关键语义样本通过。
- 2026-09-22：完整离线测试 74 项通过；圈客新增 6 项覆盖负向/跨主题上下文、三层结果与优先集合交接、模型错误/非法协议、伪造或跨客户引用、一般咨询强塞优先、同主题撤回忽略及可信范围绑定。单 Plan/停止语义既有回归继续通过。
- 2026-09-22：独立真实模型圈客语义评测使用 `deepseek-v4-flash` 完成，7/7 人工标注样本的需求状态、层级和必要证据引用通过；该结果不验证产品适配、生产泛化或完整业务链。


## 任务入口

- 运行完整离线测试：`.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -p "test_*.py" -v`
- 运行 Demo V1 合成端到端冒烟：`.\.venv\Scripts\python.exe scripts\smoke_demo_v1.py`
- 编译检查：`.\.venv\Scripts\python.exe -m compileall -q src tests scripts`
- Agent Runtime 离线冒烟仍为：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts\smoke_agent_loop.py`
- 运行真实模型洞察冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts\smoke_real_insight_agent.py`
- 校验共享合成快照：`.\.venv\Scripts\python.exe scripts\validate_insight_mock_data.py`
- 真实模型圈客语义评测入口：`scripts/evaluate_customer_selection_model.py`
