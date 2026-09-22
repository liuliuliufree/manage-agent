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
- `data/client/` 与 `data/product/` 已保存按 M4 设计生成的 50 位客户、115 条行为、主题/素材字典、产品原文索引、manifest 和 README；`scripts/validate_insight_mock_data.py` 可用标准库从实际文件计算统计和 SHA-256，并校验引用、配额、时间、去重口径及独立反例。
- `src/application/insight_tools.py` 提供三个可独立装配的只读 `Tool`：`search_knowledge`、`read_knowledge`、`aggregate_records`。它们从受信配置绑定的本地 Markdown/Mock 快照读取或计算，使用白名单字段、别名精确解析、文件/manifest 指纹、左闭右开时间窗、同事件筛选、分组独立客户去重和显式分母；不接入 Capability、Planner、API 或前端，不生成 Opportunity、推荐、预测 NBEV 或客户名单。
- `scripts/smoke_real_insight_agent.py` 提供真实 OpenAI-compatible 模型的洞察 Tool-Call 冒烟：要求模型完成知识检索、原文读取和实际快照统计，并对工具调用、105/40/15 统计、限制说明及禁止业务结论做确定性验收。该脚本仍是评测入口，不是生产 Agent 或 M4 Capability。
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

- 当前没有真实定向洞察、圈客、策略、产品知识接入、客户数据接入、客户归属/渠道规则或任务分发能力。三个 M4 只读工具只提供原文检索/读取和受控统计，尚未形成洞察 Capability；测试使用合成快照，只验证工具协议、来源校验和统计口径。
- 当前没有 HTTP API、运行持久化、认证、会话恢复、并行调度、外部事务或跨 Goal/跨 Plan 产物复用。
- Parser 受治理指标词汇当前仅包含 NBEV；产品名称只作为用户原文保存，不验证真实在售或适配性。金额解析不支持中文数字、区间、算式、负数、零或 at_most 等比较意图。
- Planner 不在规划期证明全部输入可达；缺输入由执行前门禁确定性阻止。模型是否能在真实输入下稳定选择最少合理能力仍需在线评测。
- 已检测到本地模型配置，但本轮真实模型在线冒烟在沙箱内均返回 `MODEL_CALL_FAILED`；外部网络访问因目标端点未确认可信而未获授权。因此没有完成真实模型语义验证，离线 FakeModel 结果不能替代该验证。
- `web/` 尚未接入当前 Application 契约，本轮未验证前端构建。

## 最近验证基线

- 2026-09-21：`import src.application` 通过。
- 2026-09-21：完整离线 `unittest` 共 62 项通过，覆盖 Domain、Parser、Planner、BusinessAgent 门禁、Catalog/handler 交集、单 Plan 停止语义、ArtifactStore、实际对象内容传递、运行隔离和规则阻断保留。
- 2026-09-21：`src`、`tests`、`scripts` 字节码编译通过。
- 2026-09-22：`scripts/smoke_demo_v1.py` 两个端到端合成样例均完成，均只生成 Plan V1，并输出可读取中文的结构化全流程日志及 `execution_mode=simulated` 的个险模拟任务。
- 2026-09-22：M4 合成快照校验通过：50 位客户、115 条行为，主窗口/历史事件 105/10，近期活跃客户 40，独立反例夹具 7 项通过；未执行 M4 洞察能力或完整 Demo 验证。
- 2026-09-22：三个 M4 只读工具离线测试 5 项通过，覆盖知识别名与原文指纹、非法参数/路径边界、客户年龄分母、同事件筛选、主题去重和源数据变体；未执行 M4 洞察 Capability 或完整 Demo 验证。
- 2026-09-22：新增真实模型洞察 Tool-Call 冒烟脚本；本轮仅完成脚本编译检查，未将真实模型在线结果写入验证基线。
- 2026-09-21：真实模型在线验证未完成，原因见已知限制。

## 任务入口

- 运行完整离线测试：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- 运行 Demo V1 合成端到端冒烟：`.\.venv\Scripts\python.exe scripts\smoke_demo_v1.py`
- 编译检查：`.\.venv\Scripts\python.exe -m compileall -q src tests scripts`
- Agent Runtime 离线冒烟仍为：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts\smoke_agent_loop.py`
- 运行真实模型洞察冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts\smoke_real_insight_agent.py`
- 校验 M4 合成快照：`.\.venv\Scripts\python.exe scripts\validate_insight_mock_data.py`
