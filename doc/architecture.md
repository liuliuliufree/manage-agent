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
├─ smoke_model.py                 使用本地配置验证真实模型连接
├─ smoke_agent_loop.py            使用 FakeChatModel 离线验证工具调用闭环
└─ generate_demo_mock_data.py     生成并重算校验前三幕合成 CSV 场景

data/scenarios/demo_acts_1_3_v1/
├─ source/                   业务运行可读取的 12 份合成原始数据 CSV
└─ test_expectations/        仅供测试断言使用的期望结果 CSV

tests/
└─ test_demo_mock_data.py    校验场景业务不变量与逐字节可重复生成
```

## 依赖方向

```text
Agent Core
      ↓ ChatModel
模型调用层
      ↓ OpenAI Python SDK
OpenAI-compatible 接口
```

前三幕 Mock 数据当前不进入 Agent Core。生成脚本只负责创建场景事实并验证数据自洽；后续业务 Tool 将读取 `source/`，测试代码可以额外读取 `test_expectations/`。
