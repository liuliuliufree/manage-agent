# Planner Demo V1 范围与开发说明

状态：已确认首版收缩方向；本文为首版实施依据，待实现、待验证

创建日期：2026-09-21

> 当前 Demo 范围：Goal 分析、机会发现、圈客和策略执行，每次请求只生成并执行一个 Plan。不实现 Replan，NO_RESULT 停止；追踪反馈、剩余目标调整和再次经营延后。以 AGENTS.md 的最新项目原则为准。下文编写时事实不代表重规划仍是首版要求。

## 1. 目的与优先级

目标是尽快交付能接入现有 BusinessAgent 的轻量 Planner，而不是先建设完整规划治理体系。用户已要求提供可直接交给后续模型执行的开发文档，因此本文明确协议、文件范围、开发顺序和验收要求。

对于 Planner 首版实施范围，本文取代 `2026-09-21-planner-convergence.md` 中完整规划结果、正式步骤身份映射、受控 Planning Context、完整 Capability View、静态输入路径校验、语义重试和先拆包后迁移的要求。原文保留为后续设计参考。项目可信身份、确定性规则、版本化事实和轻量 Plan 边界继续有效。

本任务只交付 Planner 和必要的 BusinessAgent/Executor 接入。真实经营 Capability、产物传递、业务规则、HTTP API 和页面属于后续任务，不得将本任务完成表述为完整 Demo 可运行。`capability-artifact-flow`、`replan-convergence` 中的完整设计不作为本任务的附带施工清单；本文也不改写它们的长期设计结论。

先完成 `2026-09-21-goal-parser-demo-v1.md` 的 Parser 公共入口，再开展本任务的完整集成验收。不得恢复整份旧 Parser 或绕开它的门禁来让测试通过。

## 2. 编写时的工作区事实

以下为 2026-09-21 文件检查结果，未执行测试：

- Planner 实际位于 `src/application/planner/planner.py`，校验位于同目录 `plan_validation.py`；不是事实文档仍描述的顶层模块。
- 执行组件位于 `src/application/capability/`。
- Planner 已有动态能力选择、依赖、一次格式修复、Plan 构造和 NO_RESULT Replan。
- BusinessAgent 已有 Parser 门禁、串行执行及最多一次 NO_RESULT Replan 的代码。
- Catalog 目前只有五类能力的描述；Executor 保存独立 handler 映射，未向装配层提供公开的可执行能力集合。
- `execute_step()` 只记录结果，没有前序产物到后继输入的受控传递。
- Goal Parser 的公共入口为空，旧实现及对应测试在工作区处于删除状态；Application 仍导入这些符号。
- `tests/application/` 当前仅有初始化文件，不能假定历史 Planner 测试仍存在。
- 源码使用 `src.*` 导入。当前不能根据历史测试记录声称业务入口可运行。

实施前重新检查 `git status --short` 和实际文件；保护用户后续修改，不执行 reset、clean 或整目录覆盖。

## 3. 必做与不做

### 3.1 首版必做

1. 输入结构化 Goal、简单引用 Context 和本次可执行 Catalog，生成非空 Plan。
2. 模型可选择单个或多个能力，可以跳过、重复和重排；不把五类能力变成固定五步。
3. Application 决定 Plan ID、版本、GoalRef 和 ACTIVE 状态；模型只生成步骤及依赖。
4. 验证输出协议、能力白名单、step ID 唯一、依赖存在、自依赖和依赖环。
5. BusinessAgent 只把同时具有 Catalog 描述和已注册 callable handler 的能力交给 Planner。
6. 区分可规划、当前无法规划和技术失败；无法规划或失败时执行 handler 的次数为零。
7. 正常规划调用一次模型；只对 JSON 语法错误保留一次格式修复，不新增语义重试。
8. 每次运行最多形成一个 Plan；断开 Demo 重规划入口，NO_RESULT 停止并返回无结果。

### 3.2 首版明确不做

- 五种规划状态及“已满足目标”的确定性证明。
- 临时别名到正式 step ID 的映射、跨运行步骤身份管理。
- 新建 PlanDraft、PlanningContext、CapabilityView 等通用对象体系。
- 跨 Goal/会话产物复用、有效期治理、产物注册中心。
- 在规划阶段沿依赖图证明全部必需输入可达。
- 副作用分类体系、控制策略注册、动态可用性探测。
- 语义重试、Fallback、Resume、并行调度、新 Agent 或新框架。
- 全量 Plan 生命周期与版本历史治理。
- 真实业务能力、数据与规则建设，前端和 API 改造。
- 为了目录对称或单一职责再拆出多个包。

不做规划期输入证明不等于允许执行缺输入的能力；后续业务接入必须在执行前检查实际输入，在任务创建/分发前执行确定性权限和经营规则。

## 4. 公共接口：尽量保留现状

### 4.1 Planner

保留现有构造参数以及以下调用形态：

```python
await planner.plan(goal=goal, context=context, capability_catalog=catalog)
```

正常返回已有 Domain `Plan`，不新增统一 Result 包装，不修改 Domain。

在现有 `planner.py` 中增加两个普通异常类：

- `PlanningUnavailableError`：当前无可规划能力，或模型按有效协议表示无法规划。
- `PlannerError`：模型调用、输出协议或 Plan 校验失败。

两类异常均具有 `code: str` 和面向用户的安全 `message: str`；异常文本不得直接透传 SDK 响应、配置或输入原文。不要再增加错误继承树。更新 `src/application/__init__.py` 的导出，保留现有 Planner 导入方式。

`plan()` 的无能力输入返回 `PlanningUnavailableError`，调用模型零次。旧 replan 方法不属于首版能力，不要求兼容或扩展，Demo 入口必须不可达。

### 4.2 BusinessAgent 映射

| Planner 结果 | BusinessAgent 行为 |
| --- | --- |
| 正常 Plan | 进入既有 ExecutionContext 与执行循环 |
| 首次规划 PlanningUnavailableError | STOPPED，携带 Goal、安全 message，无 Plan、不执行能力 |
| 首次规划 PlannerError | FAILED，携带稳定错误码和安全提示，不执行能力 |
| Capability NO_RESULT | STOPPED，保留当前 Plan、Context 和最近结果，说明无结果，不再规划 |
| 缺信息、部分成功、阻断或失败 | 按各自状态提示并结束运行，不生成第二个计划 |

不要为上述映射新增 BusinessAgentStatus。已有 Parser 澄清和技术失败分支优先执行，不能为了检查空 Catalog 跳过 Parser 门禁。新增异常应在当前宽泛异常捕获之前处理。

## 5. 模型协议

### 5.1 正常规划

保留当前输出，无需为成功情况增加 status 字段：

```json
{
  "steps": [
    {"step_id": "inspect", "capability_id": "directional_insight", "depends_on": []},
    {"step_id": "target", "capability_id": "customer_targeting", "depends_on": ["inspect"]}
  ]
}
```

以上仅为输出格式示例，不是固定计划或 Prompt 中的固定流程要求。

### 5.2 当前无法规划

```json
{"unable_to_plan": true}
```

这是首版唯一新增模型分支，映射 `PlanningUnavailableError(code="PLANNING_UNAVAILABLE")`，使用应用固定提示：“当前可用能力无法形成处理此请求的计划，请调整请求或接入相应能力。”

这表示规划器本次未形成计划，不是确定性证明所有经营路径都不可能。不给模型自由文本理由直接充当已核实能力缺口，不实现 UNSUPPORTED 的证明机制。Prompt 要求仅在无法用所给能力组织行动时返回该分支，不能用它掩盖格式错误。

该协议仅用于首次规划，没有 Replan 模型协议或第二轮规划。

### 5.3 严格解析规则

- 顶层恰为 `steps` 或恰为 `unable_to_plan`，不能混用；后者必须是 JSON 布尔值 true。
- steps 必须是非空数组，每步恰含 step_id、capability_id、depends_on。
- 两个 ID 为非空字符串，首尾空白规范化后校验；depends_on 为非空字符串元素组成的数组，允许空数组。
- 不把数字、null、字符串依赖列表强制转为合法类型。
- Plan ID、版本、GoalRef、状态等额外字段作为协议错误拒绝，不接受模型覆盖。
- 空 Plan 不表示无需行动；协议失败不转换为无法规划。

首次协议收紧可能改变旧宽松行为，必须通过测试和开发日志明确记录。

## 6. 模型输入与可执行 Catalog

### 6.1 简单引用 Context

保留 `ExistingContext = Mapping[str, Sequence[str]]`，不建立新的 Context 类型。

- None 规范化为空字典。
- 键必须为非空、以 `_refs` 结尾的字符串；值必须为 list/tuple，每项为非空字符串。拒绝裸字符串，避免被拆成字符列表。
- 规范化后复制，不修改调用方容器；拒绝 payload 字典等任意对象。
- Context 由 Application 提供，不从模型或用户消息提取可信引用；只向模型传引用，不传客户画像。
- 这里只验证容器形态，不声称引用真实存在、有效或有权限。实际对象解析和授权属于业务执行入口。
- 不扩展为跨 Goal/会话复用；有旧结果的测试可由应用显式传入合成引用。

无效 Context 在模型调用前返回 `PlannerError(code="PLANNING_CONTEXT_INVALID")`。

### 6.2 能力过滤

在现有 `CapabilityExecutor` 增加只读属性 `available_capability_ids: frozenset[str]`。构造时检查 handler 为 callable；非 callable 是装配错误，直接 ValueError，不当作当前可用能力。

BusinessAgent 在调用首次规划前构造 Catalog 与此集合的交集：

- Catalog 描述与 handler 映射保持独立。
- 不访问 Executor 私有 `_handlers`，不新增 Registry。
- 交集保持 Catalog 原有内容和顺序；顺序没有业务流程意义。
- 无 handler 的能力不发送模型；未在 Catalog 声明的 handler 不发送模型。
- 后续 `validate_plan()` 也使用这一交集，不能重新使用完整 Catalog。
- 交集为空时首次规划返回无法规划；BusinessAgent 应允许空 Catalog 经 Parser 门禁后到此分支，替换当前构造函数的空 Catalog 拒绝。
- 直接调用 Planner 时 Catalog 是调用方声明的可用能力集，Planner 不导入 Executor、不探测 handler。

这仅证明 callable 已装配，不证明外部服务健康或业务一定成功。后续业务能力接入时再补真实输入输出说明，本任务不虚构元数据。

## 7. 校验、错误与模型调用上限

处理顺序固定为：输入检查 → 模型调用 → JSON 解码 → 协议校验 → 步骤构造 → Plan 构造及确定性校验 → 返回。

| 情况 | 结果与 code | 模型调用次数 |
| --- | --- | --- |
| 空可用 Catalog | PlanningUnavailableError / PLANNING_UNAVAILABLE | 0 |
| 无效 Context | PlannerError / PLANNING_CONTEXT_INVALID | 0 |
| 模型调用异常 | PlannerError / PLANNER_MODEL_FAILED | 1，不自动重试 |
| 空响应、合法 JSON 但类型/字段不符合协议 | PlannerError / PLANNER_PROTOCOL_INVALID | 1 |
| JSON 语法错误 | 仅一次格式修复；仍错误为 PLANNER_PROTOCOL_INVALID | 最多 2 |
| 非空步骤但能力未知、重复 ID、非法依赖 | PlannerError / PLAN_INVALID | 1，不语义重试 |
| 有效 unable_to_plan | PlanningUnavailableError / PLANNING_UNAVAILABLE | 1 |

仅 `json.JSONDecodeError` 触发格式修复，不再将所有 ValueError 视为可修复错误。修复调用异常映射 PLANNER_MODEL_FAILED；修复后仍必须完成所有校验。修复提示只允许更正 JSON 格式，不能要求补步骤或改能力。代码不宣称能证明模型修复前后语义完全一致。

Plan ID/GoalRef/版本/状态继续由应用构造。step ID 暂由模型生成，作用域为本次运行；拒绝重复 ID，但不建设全局命名服务。

保持当前 Planner 模块，不为未来 Replan 预建共享层。一次 JSON 格式修复发生在正式 Plan 创建前，不属于执行结果驱动的重规划，不新增语义重试。

## 8. 单次计划与停止边界

- Demo 不构建、不调用 Replan，不生成 Plan V2，不复用跨计划产物。
- continuation.py 将 NO_RESULT 映射为 STOP；BusinessAgent 返回 STOPPED 和安全的无结果说明，保留当前结果。
- BusinessAgent 移除自动重规划调用、预算计数及 current_plan 换版分支；不能只靠 Prompt 禁止重规划。
- 缺信息返回澄清并结束本次运行；PARTIAL_SUCCESS、BLOCKED、FAILED 停止，不自动换路径。
- 同步 step_resolution.py 和 continuation.py：仅 SUCCESS 释放依赖或判定全部步骤完成，PARTIAL_SUCCESS 不自动推进。
- 用户补充后重新提交完整请求，视为新运行，不续接旧 Plan。
- 不为旧 Replan 接口增加兼容层或测试；旧方法可暂留为未接入代码，不要求全面删除历史代码和 Domain 版本字段。测试使用调用即失败的 replan 替身，确认入口不可达。
- 此处是待实现要求；已有 Replan 代码不能描述为已禁用。

## 9. 文件边界

| 文件 | 允许修改的职责 |
| --- | --- |
| src/application/planner/planner.py | 协议、输入检查、安全异常、模型调用、单次 Plan 构造 |
| src/application/planner/plan_validation.py | 首次 Plan 基础校验，不新增 Replan 校验 |
| src/application/capability/capability_executor.py | callable 检查和公开只读能力集合 |
| src/application/business_agent.py | 可用 Catalog 交集、结果映射、断开重规划入口 |
| src/application/capability/continuation.py、step_resolution.py | NO_RESULT 停止，仅 SUCCESS 推进，部分成功停止 |
| src/application/__init__.py | 必要导出 |
| tests/application/test_planner_demo_v1.py | Planner 协议和校验测试 |
| tests/application/test_planner_integration.py | Executor/BusinessAgent 门禁与不重规划验证 |
| scripts/smoke_planner.py | 若存在则适配；需要在线验证时可创建最小脚本 |

不修改 Domain、Model、Agent Runtime、Goal Parser、Web，不新增依赖。已有调用方若因本次公开异常和协议变更需要适配，只做必要适配并说明。前置 Parser 尚未完成时先报告集成阻塞，不能通过临时导入绕过或伪造模块解决。

## 10. 开发顺序

1. **确认基线。** 阅读事实文档、本文和 Parser V1，检查工作区与公共导入。记录已有失败，不复用历史通过数字。
2. **完成 Planner 协议。** 保留 Plan 返回值，增加两个异常、无法规划分支、严格输入输出校验及受限格式修复。
3. **接入可用能力。** Executor 提供只读集合；BusinessAgent 对首次规划过滤并映射异常。
4. **收缩执行入口。** NO_RESULT 映射 STOP，移除重规划计数、调用及换版分支，验证一次运行只有一个 Plan。
5. **完成离线验证。** 使用 FakeChatModel 和合成 handler，无网络依赖；修复本次引入的失败。
6. **同步事实文档。** 更新真实目录、接口、限制和实际验证结果。任务完成后停止，不顺手施工业务数据流或页面。

## 11. 验收矩阵

测试使用现有 `src.model.fake.FakeChatModel`；通过 requests 检查模型输入及调用次数，通过 handler 计数检查执行门禁。BusinessAgent 测试可注入返回真实 GoalParseResult 的 Parser 测试替身，但不得用它替代公共入口导入验证。

| 编号 | 场景 | 必须验证 |
| --- | --- | --- |
| T01 | 单能力规划 | 返回一项 Plan，应用控制身份/版本/GoalRef/ACTIVE |
| T02 | 已有 opportunity_refs/customer_refs | 传入引用完整；模型返回后续单能力时不补前置步骤 |
| T03 | 重复同一能力与独立步骤 | 不同 step ID 合法；无固定五步或强制依赖 |
| T04 | 未知能力、重复 ID、未知依赖、自依赖、环 | 参数化拒绝，无语义重试 |
| T05 | 空步骤、错误字段/类型、额外身份字段、矛盾分支 | PLANNER_PROTOCOL_INVALID，不修复合法 JSON |
| T06 | JSON 语法错误 | 合法修复成功；仍非法停止；最多两次模型调用 |
| T07 | unable_to_plan | 无 Plan；BusinessAgent STOPPED；handler 调用零次 |
| T08 | SDK 异常及空响应 | 安全错误码；敏感异常文本不进入用户响应 |
| T09 | Context 形态 | 裸字符串、非引用键、任意 payload 拒绝；原输入未修改 |
| T10 | Catalog/handler 交集 | 无 handler 能力不发给模型；模型仍选它则拒绝 |
| T11 | 空交集 | Parser 正常后 STOPPED；Planner 模型调用零次；handler 零次 |
| T12 | handler 非 callable | 装配时明确报错，不进入模型 |
| T13 | Parser 澄清/技术失败 | 不调用 Planner、不执行 handler，保持 Parser V1 行为 |
| T14 | 正常集成 | 合成 handler 完成既有串行执行；不声称证明真实产物传递 |
| T15 | NO_RESULT | STOPPED，保留结果；replan 调用零次，无 Plan V2 |
| T16 | 部分成功、阻断或失败 | 停止且保留结果，不生成第二个 Plan、不自动重试 |
| T17 | 用户重新提交 | 新独立运行，不继承旧 Plan、step_results 或运行产物 |
| T18 | 换经营阶段、金额、产品输入 | 不改 Planner 代码；传入 Goal 不被覆盖 |

FakeModel 证明代码按协议处理模型结果，不能证明真实模型会正确选择能力。T02 不应只断言测试替身输出，还应检查发给模型的 Context、Catalog 和“不机械补齐能力”规则。

从仓库根目录使用 PowerShell：

```powershell
.\.venv\Scripts\python.exe -c "import src.application; print('application import ok')"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
git diff --check
```

解释器不存在时检查已有环境，不擅自安装工具。真实模型已配置时，补少量只规划、不产生外部写操作的冒烟：仅看机会、已有机会圈客、已有客户生成策略。检查实际能力选择、协议及无固定流程；未配置则明确记录未执行在线验证。不得打印密钥。

## 12. 本任务之后的完整 Demo 缺口

以下不在本开发任务中实现，但完整 Demo 必须继续补齐：

1. 版本化合成客户、产品知识与规则，以及真实返回可追踪结果的业务 Capability/Tool。
2. 当前运行内的最小产物传递：显式输出引用、类型和来源步骤；后继只读取允许的初始及依赖产物；执行前检查实际必需输入。
3. 创建模拟经营任务前强制校验客户归属和个险可经营范围；银保等不允许对象必须被确定性阻断，失败结果不得伪装成成功产物。
4. 策略执行落为通过确定性校验的模拟任务或模拟分发，展示执行结果；反馈、剩余目标调整和再次经营延后。本次执行完成不等于 NBEV 目标已达成。
5. API 和页面接通，以及完整链路、跳步、缺输入和越权阻断的业务验收。

这些需求分别按真实能力收敛，不因本文引用而自动要求实现原设计里的完整产物治理、恢复体系或生命周期框架。

## 13. 完成标准与文档同步

- 本文首版功能与验收矩阵完成，公共导入正常，无额外框架或 Domain 改动。
- 不将空计划、协议失败或模型判断伪装成已完成目标。
- current-state 记录现行能力、限制与带日期的实际验证结果，移除与代码矛盾的路径和 Planner 行为。
- architecture 对齐现有 planner/capability 目录、过滤 Catalog 与错误处理边界。
- dev-log 的 Unreleased 记录实际功能变更及测试结论，不复制历史测试数量。
- 最终报告区分离线验证、在线验证和未完成的业务 Demo；本任务不要求将整个 Demo 做完。

## 14. 可复制给开发模型的任务

> 请按 `doc/design/2026-09-21-planner-demo-v1.md` 实现 Planner Demo V1。先阅读 AGENTS.md、当前事实文档和本文，检查工作区并保护已有修改。确认 Goal Parser V1 公共入口可用，未完成时报告前置集成阻塞，不恢复旧 Parser。本文取代原 planner-convergence 的完整首版要求。严格使用本文的 Plan 返回值、两个安全异常、模型 JSON 协议、可执行 Catalog 交集和调用上限，只生成并执行一个 Plan，NO_RESULT 停止，不构建或调用 Replan；按文件边界、开发顺序和验收矩阵实施。不新增 Domain 对象、依赖、框架、通用产物治理或业务能力。完成后同步 current-state、architecture 和 dev-log，明确实际测试及在线验证情况，不声称完整经营 Demo 已可运行。
