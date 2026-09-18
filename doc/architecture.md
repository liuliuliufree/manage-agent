# 当前架构

## 关键目录与职责

```text
src/domain/
├─ goal.py          版本化经营目标、缺失信息与假设
├─ evidence.py      带来源、版本与有效期的最小证据
├─ opportunity.py   关联 Goal/Evidence 的经营机会判断
├─ capability.py    稳定 Capability 请求、结果与状态契约
├─ plan.py          Capability Plan 与轻量步骤依赖校验
└─ refs.py          Goal/Plan 的版本化引用

src/agent/
├─ event.py         Trace、Turn、Tool 生命周期事件
├─ tool.py          Tool 定义和 JSON Schema 参数校验
├─ trace.py         Trace、Turn 与 ToolExecution 状态
└─ loop.py          多 Turn 模型调用、工具执行和终止控制

src/model/
├─ contract.py      ChatModel 契约
├─ settings.py      OpenAI-compatible 配置
├─ openai_chat.py   真实流式模型实现
└─ fake.py          确定性测试模型
```

## 依赖方向

```text
未来 Application（M2）
       ├──→ Domain
       └──→ Agent Runtime ──→ Model
```

`domain` 不导入 `agent` 或 `model`；`agent` 与 `model` 也不导入 `domain`。未来 Application 是唯一可同时组合领域契约和通用 Runtime 的位置。

## 领域数据流

```text
原始经营请求 + 可信上下文
              ↓
      Goal（版本化）
              ↓
      Plan（选择 Capability）
              ↓
CapabilityRequest / CapabilityResult
              ↓
Opportunity ← Evidence
```

M1 仅描述上述对象及其机器可校验不变量；没有 Goal Parser、Planner、Capability Runtime、业务 Tool、数据持久化或 HTTP API。CapabilityResult 的 `execution_meta.trace_id` 是字符串引用，避免 Domain 依赖 Agent Trace 类型；`rule_result_refs` 统一保存 `RULE_RESULT` Evidence ID，并由后续 Application 在可取得 Evidence 集合时解析类型。

## M1 已强制的契约

- Goal、Plan 版本不低于 1，`revise()` 创建新版本而不修改旧实例。
- Evidence 必须带非空 Source；EvidenceType 不包含 Agent judgement。
- 正式 Opportunity 必须指向具体 Goal version 且至少保留一条 EvidenceLink；优先级需要解释因素。
- Capability 状态语义区分无结果、业务规则阻断和运行失败；BLOCKED 要求规则结果引用。
- PlanStep 只选择 Capability，可重复、可省略；依赖必须存在且不能成环。

产品、客户、规则与 Trace 的事实来源，以及 Opportunity/Capability 语义是否被错误设计为固定 Demo 工作流，仍由后续实现与架构评审保证。
