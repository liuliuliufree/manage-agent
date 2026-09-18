# 当前实现状态

## 当前能力

- `src/model/` 提供 `ChatModel` 契约、OpenAI-compatible 配置、真实模型实现、FakeModel 和模型错误类型。
- `src/agent/` 提供 Tool 定义与参数校验、Trace/Turn/ToolExecution 状态、生命周期事件，以及支持模型流式输出和 Tool 调用的多轮 Agent Loop。
- Agent Runtime 仅依赖模型、消息和 Tool 协议，不感知开门红、客户、产品或 NBEV 等经营概念。
- `src/domain/` 提供不依赖 Agent/Model 的 M1 领域契约：版本化 Goal、可追溯 Evidence、Evidence 驱动的 Opportunity、Capability 请求/结果和轻量依赖 Plan。
- `tests/domain/` 使用标准库 `unittest` 覆盖 M1 核心契约、状态不变量、Plan 依赖校验和跨场景数据结构。
- `web/` 保留 React/Vite 前端及 SSE 客户端和对话界面代码，但当前仓库已无对应的 `src/manage` 后端 API；前端不能据此宣称已有完整业务 Demo 闭环。
- `doc/roadmap/` 包含总体路线和 M1 任务拆分；`doc/design/` 保存此前运行时及页面方案的设计记录，未自动视为当前实现。

## 核心契约与边界

- 依赖方向为未来 Application → `src/domain`，以及未来 Application → `src/agent` → `src/model`；Domain 与 Agent/Model 相互独立，底层 Runtime 不反向依赖智慧经营业务模块。
- Tool 是可执行的技术/业务接口；Capability 属于上层业务语义，可在未来组合一个或多个 Tool，二者不可混为一谈。
- 当前没有 Goal Parser、Planner、Capability 执行实现、确定性经营规则、客户数据或任务分发能力；Plan/CapabilityResult/Opportunity/Evidence 目前仅为领域数据契约，不执行任何业务逻辑。
- 当前没有认证、会话历史、运行持久化、生产级并发治理或真实业务数据接入。
- 仓库中的合成数据与业务规则已随最近提交移除，不能再以此前的 86→41→12 漏斗、机会推荐或客户结果作为当前事实。
- 最近验证基线：2026-09-17，M1 领域契约 `unittest` 13 项通过，并完成 `src` 与 `tests` 字节码编译。

## 已知限制

- `src/manage` 已不存在，因此 README 中关于 `manage.api`、`manage` 命令行入口和业务 Tool 自动发现的说明与当前代码不一致，待后续业务层重建时同步校准。
- 前端仍保留旧的对话接入形态，缺少当前可用的后端业务入口；前端构建状态未在本轮重新验证。
- M1 不校验 Opportunity 文本是否暗含产品推荐、Capability 是否被错误设计成固定流程、或 Runtime 是否在未来被错误接入 Domain；这些仍需架构评审与后续集成测试。
- 下一阶段可在 M1 契约之上进入 Goal 解析、运行时规划和业务能力实现；不应把路线文档中的设计目标当作已完成能力。

## 任务入口

- 阅读路线：`doc/roadmap/roadmap.md`
- 阅读 M1 任务：`doc/roadmap/M1/M1.md` 及 `doc/roadmap/M1/T01-T02.md` 至 `T08.md`
- 运行 M1 领域契约测试：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- 运行 Agent Runtime 离线冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts/smoke_agent_loop.py`
- 运行模型冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts/smoke_model.py`
- 前端开发/构建：进入 `web/` 后执行 `npm run dev` 或 `npm run build`；当前不应假设存在可连接的业务 API。
