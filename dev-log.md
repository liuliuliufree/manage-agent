# 开发日志

## [Unreleased]

- 新增 `scripts/smoke_agent_loop.py`，离线验证 Agent Loop 的模型工具调用、工具结果回传、最终回答和 Trace 终止状态，并实时打印结构化运行日志。
- 修正 Agent Loop 对当前 `model` 包的导入，避免运行时引用不存在的包名。
