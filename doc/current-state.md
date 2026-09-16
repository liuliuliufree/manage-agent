# 当前实现状态

## 系统快照

项目具备 OpenAI-compatible 模型调用层、可观察的 Agent Loop、自动发现的业务 Tool、通用经营 Agent、FastAPI SSE 接口和 React 对话前端。

一次用户请求创建一个独立 Trace；Trace 由多个 Turn 组成。每个 Turn 可以产生模型文本和一个或多个 Tool 调用，模型观察 Tool 结果后自主决定下一步，直到直接回答或达到工具轮次上限。应用层不规定固定幕次、必经工具、固定机会或固定产物，也不在模型漏调工具时暗中补跑预设流程。

当前合成数据仍可稳定展示原前三幕故事：读取经营目标与边界、比较三个机会、推荐重点机会、执行客户筛选并按需解释客户证据。这是当前数据与工具能力的展示，不是 Agent 的阶段模型。

## 当前能力

- `src/manage/tools/` 中每个非私有模块通过 `create_tool(context)` 声明一个 Tool；运行时按模块自动发现并暴露给 Agent。
- 当前提供经营上下文、机会分析、机会客群筛选和客户决策证据四个确定性 Tool；四者可独立调用，不存在代码强制调用顺序。
- `src/manage/prompts/` 保存稳定角色提示词和运行时消息模板；提示词要求模型自主选取工具，不假设固定流程。
- `src/manage/agent.py` 创建单次运行、Trace、Turn 和工具上下文，并同时支持事件流与完整结果。
- `src/manage/api.py` 提供真实的 `POST /api/chat/stream` SSE 接口，流式返回 Trace、Turn、Tool 输入与结果、模型公开文本和终止事件。
- React 前端默认请求真实后端，并按 Turn 分组模型公开的中间说明，动态渲染实际 Tool 及可展开的结构化结果；没有固定三幕数组或内置答案流。
- 当前合成数据仍能重算三个机会及第一类机会的 86→41→12 漏斗，并返回可追溯的客户级规则和评分证据。

## 核心契约与边界

- Agent Core 不感知具体业务；`ManageAgent` 只组合模型、通用循环、提示词和自动发现的 Tool。
- 普通代码负责授权、拒绝、敏感状态、频控、适当性、指标和排序等确定性计算；模型负责理解目标、选择能力、观察结果和组织回答。
- 每次运行使用独立 `ToolContext`，其中缓存同一数据源的业务服务并记录本次实际 Tool 产物，不跨请求共享运行状态。
- Tool 参数和结果使用 `data_source_id`；底层现有 CSV 仍保留历史字段 `scenario_id`，该字段只属于当前数据格式。
- 当前数据源包含 120 名合成客户，基准时间为 2026-09-15 09:00（Asia/Shanghai）；测试期望与业务 source 隔离。
- 高分不能覆盖任何硬规则失败。合成数据、预计响应、成本和综合分不得表述为生产事实。

## 已知限制

- 当前只有一份覆盖原前三幕故事的合成数据，尚未提供后续故事所需的数据和 Tool；新增后续能力时无需改变 Agent Loop、HTTP 事件或前端步骤模型。
- 当前请求彼此独立，尚未实现跨请求会话历史、运行持久化、认证和生产级并发治理。
- 当前确定性经营服务实现了现有三类机会规则；新机会仍需增加相应的普通代码能力或外部适配器。
- HTTP 接口依赖可用的 OpenAI-compatible 模型配置；模型不可用时返回明确错误，不伪造业务答案。

## 任务入口

- 生成并校验数据：`.\.venv\Scripts\python.exe scripts\generate_demo_mock_data.py`
- 校验已有数据：`.\.venv\Scripts\python.exe scripts\generate_demo_mock_data.py --validate-only`
- 运行 Agent：先设置 `$env:PYTHONPATH = "src"`，再执行 `.\.venv\Scripts\python.exe -m manage "<请求>"`
- 启动 API：先设置 `$env:PYTHONPATH = "src"`，再执行 `.\.venv\Scripts\python.exe -m uvicorn manage.api:app --reload`
- 运行测试：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- 启动前端：进入 `web/` 后执行 `npm run dev`
- 构建前端：进入 `web/` 后执行 `npm run build`

## 最近验证基线

2026-09-16：12 项数据、确定性业务能力、Tool 自动发现、Agent 自主调用、事件生命周期和真实 HTTP SSE 契约测试通过；前端 TypeScript 检查与 Vite 生产构建通过。生产构建因现有 `web/dist` 文件权限无法清理，使用新的临时输出目录完成，未覆盖仓库中的旧构建产物。本轮未执行真实模型冒烟和浏览器截图验证。
