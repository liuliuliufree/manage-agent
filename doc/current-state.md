# 当前实现状态

## 当前能力

- `src/model/` 提供 `ChatModel` 契约、OpenAI-compatible 配置、真实模型实现、FakeModel 和模型错误类型。
- `src/agent/` 提供 Tool 定义与参数校验、Trace/Turn/ToolExecution 状态、生命周期事件，以及支持模型流式输出和 Tool 调用的多轮 Agent Loop。
- Agent Runtime 仅依赖模型、消息和 Tool 协议，不感知开门红、客户、产品或 NBEV 等经营概念。
- `src/domain/` 提供不依赖 Agent/Model 的收敛领域契约：版本化 Goal、最小结构化 Evidence、Evidence 驱动的 Opportunity、引用式 Capability 请求/结果和轻量依赖 Plan；M4～M7 才会消费的治理字段不提前进入核心对象。
- `src/application/` 提供 M2-Lite Capability Catalog、Goal Parser、Planner，以及 M3-T01 至 T07 的最小 CapabilityExecutor、ExecutionContext、单步执行、Ready Step 解析、继续策略、`NO_RESULT` 重规划和 BusinessAgent 执行闭环；BusinessAgent 可将自然语言请求串联到 Goal、动态 Plan 和 Capability 执行，并根据结果继续、完成、询问用户、停止或最多生成一次 Plan 新版本后继续。
- `tests/domain/` 使用标准库 `unittest` 覆盖 M1 核心契约、状态不变量、Plan 依赖校验和跨场景数据结构。
- `web/` 保留 React/Vite 前端及 SSE 客户端和对话界面代码，但当前仓库已无对应的 `src/manage` 后端 API；前端不能据此宣称已有完整业务 Demo 闭环。
- `doc/roadmap/` 包含总体路线；M1 领域边界、当前契约、不变量、验证矩阵和未来扩展条件已收敛到单一 `doc/roadmap/M1/M1.md`，不再保留 T01～T08 分篇。`doc/design/` 保存此前运行时及页面方案的设计记录，未自动视为当前实现。

## 核心契约与边界

- 依赖方向为 Application → `src/domain` 和 Application → `src/model`；未来能力执行接入时可形成 Application → `src/agent` → `src/model`。Domain 与 Agent/Model 相互独立，底层 Runtime 不反向依赖智慧经营业务模块。
- Tool 是可执行的技术/业务接口；Capability 属于上层业务语义，可在未来组合一个或多个 Tool，二者不可混为一谈。
- Goal Parser 支持新 Goal、已有 Goal 的基础 SET 修改和澄清返回；未实现 CLEAR Patch Framework。模型输出不能决定 Goal ID、版本、原始请求或可信 actor/channel，模型生成的日期会被忽略，产品和需求提及必须逐字存在于用户请求。
- Planner 支持跳过、重复、重排及步骤依赖，并允许一次非法 JSON 格式修复；Plan ID、版本、GoalRef 和状态由 Application 构造。
- 独立 `validate_plan()` 确定性检查 Catalog 外能力、重复 step_id、未知依赖和依赖环；Planner 在返回 Plan 前调用该函数。
- BusinessAgent 依次调用 Goal Parser、澄清分支、Planner、Plan Validation 和最小执行循环，对外区分 `COMPLETED`、`CLARIFICATION_REQUIRED`、`STOPPED` 与应用异常 `FAILED`；执行循环直接组合已有函数，不是新的 Agent Loop、Workflow Engine 或状态机。
- 当前已有 Capability 的最小 handler 分发、失败收敛、ExecutionContext 结果记录、PlanStep 单步执行链路、Ready Step 解析、执行后继续策略和 `NO_RESULT` 后的 Plan 版本重规划；BusinessAgent 会自动推进成功步骤，最多允许一次 Replan，保留旧步骤结果并避免已成功步骤重跑。没有 Retry、Fallback、Resume、并行调度、自动合并输出、确定性经营规则、客户数据或任务分发能力；Plan/CapabilityResult/Opportunity/Evidence 自身不执行任何业务逻辑。
- Capability Catalog 与执行 handler 映射保持分离：Catalog 面向 Planner 描述“能做什么”，Executor 的普通映射决定“由谁执行”；缺失 handler 或 handler 异常会返回既有 M1 `FAILED` CapabilityResult。
- ExecutionContext 仅包含 `goal`、`current_plan`、`known_context` 和 `step_results`；`record_result()` 只按 step_id 保存最新结果，不把输出自动并入已知事实。
- `build_capability_request()` 直接使用当前 Goal/Plan 版本、Goal 中的可信 actor/channel 来源，并只把 `known_context` 中命名为 `*_refs` 的字符串引用收敛为 `input_refs`；不再透传开放式业务属性。`execute_step()` 只负责构造请求、调用 Executor 并记录结果，不判断步骤是否 Ready。
- Goal 不重复保存可由 `metric + target` 推导的完成标准；Evidence 以 `subject_ref/field/value`、来源、观测/有效时间及可选置信度和限制表达最小判断依据；Opportunity 复用 `GoalRef`，核心只保留问题、证据链接及可选的轻量优先级；PlanStep 仅保留能力选择和依赖。候选筛选逻辑、机会有效性、下一步提示和写操作控制策略分别延后到其真实消费阶段。
- `is_step_ready()` 只认 `step_results`：步骤未执行且所有依赖为 `SUCCESS` 或 `PARTIAL_SUCCESS` 时 Ready；`get_next_ready_step()` 按 Plan 出现顺序返回第一个 Ready Step。它不判断 Plan 已完成、卡住或需要重规划。
- `decide_continuation()` 将 `SUCCESS/PARTIAL_SUCCESS` 映射为 `CONTINUE`、`FINISH` 或不一致状态下的 `STOP`，将 `NO_RESULT` 映射为 `REPLAN`，将 `NEED_INFORMATION` 映射为 `ASK_USER`，并对 `BLOCKED/FAILED` 返回 `STOP`；`Planner.replan()` 只处理 `NO_RESULT`，基于 Goal、当前 Plan、Context、历史结果、最近结果和 Catalog 生成完整 Plan 新版本，复用 `validate_plan()` 并通过 `validate_replan()` 防止保留的成功步骤改变 capability 身份。当前不执行 Retry、Fallback、Resume 或其他状态恢复。
- Capability Catalog 不包含顺序、前后继或步骤编号；五类能力可由后续 Planner 按 Goal 与上下文选择、跳过、重复或重排。
- 当前没有认证、会话历史、运行持久化、生产级并发治理或真实业务数据接入。
- 仓库中的合成数据与业务规则已随最近提交移除，不能再以此前的 86→41→12 漏斗、机会推荐或客户结果作为当前事实。
- 最近验证基线：2026-09-21，收敛后的领域契约、M2-Lite/M3-Lite Application 与 Goal Parser 收敛行为共 84 项 `unittest` 通过；覆盖正常多步执行、一次 Replan、部分 Goal 澄清门禁、阻塞修订版本、CLEAR、无依据字段过滤、非阻塞缺失继续规划、指标词汇来源和单次格式修复。本轮完成 `src`、`tests` 及 `scripts` 字节码编译，未执行真实模型在线验证；此前旧 Goal Parser 协议的三个在线场景不能替代新协议复验，Planner 四个首次规划场景此前在线通过，Replan 仍未在线验证。

## 已知限制

- `src/manage` 已不存在，因此 README 中关于 `manage.api`、`manage` 命令行入口和业务 Tool 自动发现的说明与当前代码不一致，待后续业务层重建时同步校准。
- 前端仍保留旧的对话接入形态，缺少当前可用的后端业务入口；前端构建状态未在本轮重新验证。
- M1 不校验 Opportunity 文本是否暗含产品推荐、Capability 是否被错误设计成固定流程、或 Runtime 是否在未来被错误接入 Domain；这些仍需架构评审与后续集成测试。
- Goal Parser 新模型协议尚未执行真实模型在线复验，也未形成跨模型行为评测；当前受治理指标词汇只包含 NBEV，其他明确指标会进入结构化澄清，扩展时必须更新版本化业务配置而不是 Prompt 或代码分支。
- `validate_plan()` 仅覆盖 M2-Lite 要求的四项基础合法性，不包含上下文依赖求解、Capability 版本绑定、输出类型、Side Effect 或语义修复。

## 任务入口

- 阅读路线：`doc/roadmap/roadmap.md`
- 阅读 M1 整体设计：`doc/roadmap/M1/M1.md`
- 运行完整 Python 测试：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- 运行 Agent Runtime 离线冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts/smoke_agent_loop.py`
- 运行模型冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts/smoke_model.py`
- 运行 Goal Parser 真实模型冒烟：`.\.venv\Scripts\python.exe scripts/smoke_goal_parser.py`
- 运行 Planner 真实模型冒烟：`.\.venv\Scripts\python.exe scripts/smoke_planner.py`
- 运行 BusinessAgent 真实模型冒烟：`.\.venv\Scripts\python.exe scripts/smoke_bussiness_agent.py`
- 前端开发/构建：进入 `web/` 后执行 `npm run dev` 或 `npm run build`；当前不应假设存在可连接的业务 API。
