# 当前实现状态

## 当前能力

- `src/model/` 提供 `ChatModel` 契约、OpenAI-compatible 配置、真实模型实现、FakeModel 和模型错误类型。
- `src/agent/` 提供 Tool 定义与参数校验、Trace/Turn/ToolExecution 状态、生命周期事件，以及支持模型流式输出和 Tool 调用的多轮 Agent Loop。
- Agent Runtime 仅依赖模型、消息和 Tool 协议，不感知开门红、客户、产品或 NBEV 等经营概念。
- `web/` 保留 React/Vite 前端及 SSE 客户端和对话界面代码，但当前仓库已无对应的 `src/manage` 后端 API；前端不能据此宣称已有完整业务 Demo 闭环。
- `doc/roadmap/` 包含总体路线和 M1 任务拆分；`doc/design/` 保存此前运行时及页面方案的设计记录，未自动视为当前实现。

## 核心契约与边界

- 依赖方向为业务层（待建设）→ `src/agent` → `src/model`；底层 Runtime 不反向依赖智慧经营业务模块。
- Tool 是可执行的技术/业务接口；Capability 属于上层业务语义，可在未来组合一个或多个 Tool，二者不可混为一谈。
- 当前没有 Goal Parser、动态 Plan、Capability 执行结果、Opportunity/Evidence 契约，也没有确定性的经营规则、客户数据或任务分发能力。
- 当前没有认证、会话历史、运行持久化、生产级并发治理或真实业务数据接入。
- 仓库中的合成数据与业务规则已随最近提交移除，不能再以此前的 86→41→12 漏斗、机会推荐或客户结果作为当前事实。

## 已知限制

- `src/manage` 已不存在，因此 README 中关于 `manage.api`、`manage` 命令行入口和业务 Tool 自动发现的说明与当前代码不一致，待后续业务层重建时同步校准。
- 前端仍保留旧的对话接入形态，缺少当前可用的后端业务入口；前端构建状态未在本轮重新验证。
- `tests/` 当前没有可发现的 `test_*.py` 测试文件；此前业务测试已随重构提交删除。
- 下一阶段应先完成 M1 业务契约及契约测试，再进入 Goal 解析、运行时规划和业务能力实现；不应把路线文档中的设计目标当作已完成能力。

## 任务入口

- 阅读路线：`doc/roadmap/roadmap.md`
- 阅读 M1 任务：`doc/roadmap/M1/M1.md` 及 `doc/roadmap/M1/T01-T02.md` 至 `T08.md`
- 运行 Agent Runtime 离线冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts/smoke_agent_loop.py`
- 运行模型冒烟：`$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe scripts/smoke_model.py`
- 前端开发/构建：进入 `web/` 后执行 `npm run dev` 或 `npm run build`；当前不应假设存在可连接的业务 API。
