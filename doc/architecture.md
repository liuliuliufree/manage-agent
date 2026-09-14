# 当前架构

## 关键目录与职责

```text
src/agent/
├─ event.py         运行过程的结构化事件契约
├─ tool.py          工具定义、JSON Schema 编译与参数校验边界
├─ trace.py         Trace、Turn 与工具执行记录
└─ loop.py          全 Turn 流式模型调用、工具执行与循环控制

src/model/
├─ contract.py      ChatModel 结构化调用契约
├─ settings.py      模型连接配置加载与校验
├─ openai_chat.py   OpenAI-compatible Chat Completions 实现
├─ fake.py          确定性测试实现
└─ errors.py        稳定的模型调用错误边界

scripts/
├─ smoke_model.py            使用本地配置验证真实模型连接
└─ smoke_agent_loop.py       使用 FakeChatModel 离线验证工具调用闭环
```

## 依赖方向

```text
Agent Core
      ↓ ChatModel
模型调用层
      ↓ OpenAI Python SDK
OpenAI-compatible 接口
```
