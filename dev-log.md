# 开发日志

## [Unreleased]

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
