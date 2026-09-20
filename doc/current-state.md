# 当前实现状态

## 当前能力

- `src/model/` 提供 `ChatModel` 契约、OpenAI-compatible 配置、真实模型实现、FakeModel 和模型错误类型。
- `src/agent/` 提供 Tool 定义与参数校验、Trace/Turn/ToolExecution 状态、生命周期事件，以及支持模型流式输出和 Tool 调用的多轮 Agent Loop。
- Agent Runtime 仅依赖模型、消息和 Tool 协议，不感知开门红、客户、产品或 NBEV 等经营概念。
- `src/domain/` 提供不依赖 Agent/Model 的 M1 领域契约：版本化 Goal、可追溯 Evidence、Evidence 驱动的 Opportunity、Capability 请求/结果和轻量依赖 Plan。
- `src/application/` 提供 M2-Lite Capability Catalog、Goal Parser、Planner 与轻量 BusinessAgent；BusinessAgent 串联自然语言请求到 Goal、澄清或动态 Plan 的完整应用链路。
- `tests/domain/` 使用标准库 `unittest` 覆盖 M1 核心契约、状态不变量、Plan 依赖校验和跨场景数据结构。
- `web/` 保留 React/Vite 前端及 SSE 客户端和对话界面代码，但当前仓库已无对应的 `src/manage` 后端 API；前端不能据此宣称已有完整业务 Demo 闭环。
- `doc/roadmap/` 包含总体路线和 M1 任务拆分；`doc/design/` 保存此前运行时及页面方案的设计记录，未自动视为当前实现。

## 核心契约与边界

- 依赖方向为 Application → `src/domain` 和 Application → `src/model`；未来能力执行接入时可形成 Application → `src/agent` → `src/model`。Domain 与 Agent/Model 相互独立，底层 Runtime 不反向依赖智慧经营业务模块。
- Tool 是可执行的技术/业务接口；Capability 属于上层业务语义，可在未来组合一个或多个 Tool，二者不可混为一谈。
- Goal Parser 支持新 Goal、已有 Goal 的基础 SET 修改和澄清返回；未实现 CLEAR Patch Framework。模型输出不能决定 Goal ID、版本、原始请求或可信 actor/channel，模型生成的日期会被忽略，产品和需求提及必须逐字存在于用户请求。
- Planner 支持跳过、重复、重排及步骤依赖，并允许一次非法 JSON 格式修复；Plan ID、版本、GoalRef 和状态由 Application 构造。
- 独立 `validate_plan()` 确定性检查 Catalog 外能力、重复 step_id、未知依赖和依赖环；Planner 在返回 Plan 前调用该函数。
- BusinessAgent 依次调用 Goal Parser、澄清分支、Planner 和 Plan Validation，对外仅返回 `PLAN_READY`、`CLARIFICATION_REQUIRED` 或 `FAILED`；它不是新的 Agent Loop、Workflow Engine 或状态机。
- 当前没有 Capability 执行实现、确定性经营规则、客户数据或任务分发能力；Plan/CapabilityResult/Opportunity/Evidence 不执行任何业务逻辑。
- Capability Catalog 不包含顺序、前后继或步骤编号；五类能力可由后续 Planner 按 Goal 与上下文选择、跳过、重复或重排。
- 当前没有认证、会话历史、运行持久化、生产级并发治理或真实业务数据接入。
- 仓库中的合成数据与业务规则已随最近提交移除，不能再以此前的 86→41→12 漏斗、机会推荐或客户结果作为当前事实。
- 最近验证基线：2026-09-20，M1 领域契约与 M2-Lite Application 共 40 项 `unittest` 通过，并完成 `src`、`tests` 及冒烟脚本字节码编译；8 个核心 Demo 行为场景已用 FakeModel 离线覆盖。真实模型已通过 Goal Parser 三个场景和 Planner 四个动态选择场景；BusinessAgent 在线冒烟曾完整通过，但随后暴露模型对模糊指标判断不稳定，确定性修复已通过离线回归。修复后的最近一次在线复验在第一个模型调用处明确返回 30 秒超时，尚未重新取得完整在线通过结果。

## 已知限制

- `src/manage` 已不存在，因此 README 中关于 `manage.api`、`manage` 命令行入口和业务 Tool 自动发现的说明与当前代码不一致，待后续业务层重建时同步校准。
- 前端仍保留旧的对话接入形态，缺少当前可用的后端业务入口；前端构建状态未在本轮重新验证。
- M1 不校验 Opportunity 文本是否暗含产品推荐、Capability 是否被错误设计成固定流程、或 Runtime 是否在未来被错误接入 Domain；这些仍需架构评审与后续集成测试。
- Goal Parser 当前依赖模型按 JSON 对象契约返回结果，不包含格式修复重试；当前只对一个已配置模型完成三个在线冒烟场景，尚不代表跨模型稳定性或完整行为评测。
- `validate_plan()` 仅覆盖 M2-Lite 要求的四项基础合法性，不包含上下文依赖求解、Capability 版本绑定、输出类型、Side Effect 或语义修复。

## 任务入口

- 阅读路线：`doc/roadmap/roadmap.md`
- 阅读 M1 任务：`doc/roadmap/M1/M1.md` 及 `doc/roadmap/M1/T01-T02.md` 至 `T08.md`
- 运行完整 Python 测试：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- 运行 Agent Runtime 离线冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts/smoke_agent_loop.py`
- 运行模型冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts/smoke_model.py`
- 运行 Goal Parser 真实模型冒烟：`.\.venv\Scripts\python.exe scripts/smoke_goal_parser.py`
- 运行 Planner 真实模型冒烟：`.\.venv\Scripts\python.exe scripts/smoke_planner.py`
- 运行 BusinessAgent 真实模型冒烟：`.\.venv\Scripts\python.exe scripts/smoke_bussiness_agent.py`
- 前端开发/构建：进入 `web/` 后执行 `npm run dev` 或 `npm run build`；当前不应假设存在可连接的业务 API。
