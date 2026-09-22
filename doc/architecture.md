# 当前架构

## 关键目录与职责

```text
src/domain/
├─ goal.py          版本化经营目标、缺失信息和可信上下文引用
├─ evidence.py      最小可追溯证据
├─ opportunity.py   关联 GoalRef/EvidenceLink 的机会契约
├─ capability.py    Capability 请求、结果、状态和输出引用
├─ plan.py          能力选择、直接依赖和轻量 Plan 校验
└─ refs.py          Goal/Plan 版本化引用

src/model/
├─ contract.py      ChatModel 契约
├─ settings.py      OpenAI-compatible 配置
├─ openai_chat.py   真实模型实现
└─ fake.py          确定性测试模型

src/agent/
├─ event.py         Trace、Turn、Tool 生命周期事件
├─ tool.py          Tool 定义与参数校验
├─ trace.py         通用运行轨迹
└─ loop.py          通用多 Turn Agent Loop

src/application/
├─ goal_parser/
│  ├─ __init__.py               公共入口
│  ├─ prompts.py                Demo V1 严格提取协议
│  ├─ goal_parser.py            单次模型提取、确定性校验与 Goal 构造
│  └─ metric_vocabulary.json    版本化 NBEV 指标词汇
├─ planner/
│  ├─ planner.py                单 Plan 规划、严格协议和安全错误
│  └─ plan_validation.py        Catalog、唯一 ID、依赖和环校验
├─ capability/
│  ├─ capability_catalog.py     Planner 可见能力描述
│  ├─ capability_executor.py    callable handler 分发与可执行能力集合
│  ├─ artifact_store.py         单次运行内存对象存储和 Goal 绑定
│  ├─ artifact_flow.py          IO 声明、初始引用、输入选择和发布元数据
│  ├─ execution_context.py      单 Plan 运行状态、结果和产物索引
│  ├─ step_execution.py         请求构造、结果校验和 SUCCESS 发布
│  ├─ step_resolution.py        仅 SUCCESS 释放依赖
│  └─ continuation.py           完成、澄清或停止决策
└─ business_agent.py            Parser → Planner → 单 Plan 执行入口

scripts/
└─ smoke_demo_v1.py             两个合成端到端 Demo V1 冒烟
```

M4 数据快照：

```text
data/client/
├─ customers.jsonl              客户基础资料
├─ behaviors.jsonl              行为事件
├─ topics.json / materials.json 主题与素材元数据
├─ manifest.json / README.md    快照元数据、指纹与口径说明
└─ （仅由脚本读取，不是当前业务运行时数据源）

data/product/
├─ product_catalog.json          用户提供 Markdown 产品原文索引
└─ *.md                          用户提供产品原文

scripts/validate_insight_mock_data.py
└─ 标准库离线校验、实际统计、指纹和独立反例夹具
```

## 依赖方向

```text
Application ──→ Domain
      │
      └───────→ Model

Agent Runtime ──→ Model
```

Domain 不导入 Application、Agent 或 Model。通用 Agent Runtime 不感知 Goal、Plan、客户、产品或 NBEV。当前 BusinessAgent 直接组合 Goal Parser、Planner 和 Application Capability 执行组件，不引入第二个 Agent Loop、Workflow Engine、Registry 或新框架。

Capability Catalog 与 Executor handler 映射保持分离：Catalog 描述 Planner 能看见的能力，Executor 表示本次装配中可调用的实现。BusinessAgent 取二者交集并保持 Catalog 原顺序；IO 元数据通过独立普通 Mapping 注入。

## 单次运行数据流

```text
完整自然语言请求 + 可信 RuntimeContext
                    ↓
 Goal Parser：一次模型提取 → 严格协议/原文/指标/金额检查
                    ↓
 Goal SUCCESS ──────┬──── 缺信息：CLARIFICATION_REQUIRED 并结束
                    │
 可执行 Catalog = Catalog 描述 ∩ callable handler
                    ↓
 初始 Store/引用校验 → Planner：首次且唯一一次 Plan
                    ↓
 Plan Validation → ExecutionContext（绑定 GoalRef/PlanRef）
                    ↓
 Ready Step（仅 SUCCESS 依赖）
                    ↓
 CapabilityIO → 直接依赖产物优先 / 初始引用回退
                    ↓
 CapabilityRequest → handler 读取 ArtifactStore 实际对象
                    ↓
 CapabilityResult 关联与输出校验
                    ↓
 SUCCESS：统一记录并发布 ───→ 下一 Ready Step / COMPLETED
 其他状态：只记录不发布 ───→ 澄清或 STOPPED
```

此路径中不存在执行结果驱动的 Replan、Plan V2 或产物跨计划迁移。Planner 唯一的第二次模型调用可能是首次 Plan 创建前的 JSON 语法修复；它不是 Replan，也不能修改合法 JSON 的步骤语义。

## Goal Parser 边界

Parser 的模型只接收 system 协议和本次用户请求，不接收 RuntimeContext 或已有 Goal。输出必须恰含 `goal_type`、四个可空原文字段及 products/needs/constraints 数组；任意额外字段、Markdown 围栏、前后文字、错误类型或无原文依据均整体失败。

Application 生成 Goal ID/version，保留完整 original_request，并以 RuntimeContext 构造 ChannelAndActor。量化目标要求受治理 metric 和合法 target；探索目标可不带二者，但用户明确表达而无法规范化的指标/目标仍阻塞。`existing_goal` 非空时首版拒绝修改，不调用模型。

## Planner 边界

Planner 输入的 Context 只允许 `*_refs` 到字符串 ID 列表。模型成功协议只包含非空 steps；无法规划协议只允许 `{"unable_to_plan": true}`。Application 创建 Plan ID、version=1、GoalRef 和 ACTIVE 状态，并执行 capability 白名单、step_id 唯一、依赖存在、自依赖与环校验。

模型调用异常映射 `PLANNER_MODEL_FAILED`；空响应或协议错误映射 `PLANNER_PROTOCOL_INVALID`；合法步骤协议但确定性 Plan 非法映射 `PLAN_INVALID`；无 Catalog 或有效 unable_to_plan 映射 `PLANNING_UNAVAILABLE`。只有 `json.JSONDecodeError` 允许一次格式修复。

## 产物与执行门禁

ArtifactStore 的键为 `type:id`，值为 JSON 兼容字典。put/get 均深复制；同一 ref 不覆盖。Store 每次运行只能绑定一次 GoalRef，重新提交必须新建 Store。

CapabilityIO 为每个可执行能力声明 required_inputs、optional_inputs 和 output_types。首版不提供 any-of、多值自动合并、Schema Registry 或字段绑定 DSL。evidence_refs 与 rule_result_refs 继续保留在 CapabilityResult 审计字段中，但不作为普通业务输入伪造。

输入解析按声明顺序逐类型处理：只查直接依赖步骤已发布的 SUCCESS 产物；若没有才查同类型初始引用；多候选报歧义，必需输入缺失报结构化缺失。无关步骤、祖先步骤和其他运行的对象不可见。

execute_step 在 handler 前检查 Goal/Plan 未变化、步骤属于当前 Plan、未重复执行且全部依赖 SUCCESS。handler 后检查结果类型、request_id、capability_id、允许输出类型、Store 对象存在、重复引用及每类型单对象约束。全部输出通过后才记录 SUCCESS 并发布索引。

PARTIAL_SUCCESS、NO_RESULT、BLOCKED、FAILED 和 NEED_INFORMATION 均不发布产物。BLOCKED 保留确定性 rule_result_refs，BusinessAgent 不会通过重规划绕过。Executor 捕获 handler 内异常并转为既有 FAILED CapabilityResult；框架侧协议错误使用 ArtifactFlowError 和稳定错误码。

## 当前业务与交互边界

当前生产代码只提供通用编排、对象传递和门禁机制，没有真实经营 handler。`scripts/smoke_demo_v1.py` 的机会、客户、策略、规则和任务均为虚构测试数据；模拟任务明确保存 `execution_mode=simulated`。它证明对象内容贯穿下游以及个险/当前代理人门禁可被执行框架尊重，不证明真实业务规则正确。

`data/client/` 与 `data/product/` 是独立的数据快照，校验脚本直接读取文件计算结果；当前没有任何 Capability/Tool/API/前端消费它，也没有预制 Opportunity、推荐名单、评分或 NBEV 预测。

仓库当前没有与该 Application 链路匹配的 HTTP API。`web/` 是保留的旧前端代码，不在本轮架构数据流中。
