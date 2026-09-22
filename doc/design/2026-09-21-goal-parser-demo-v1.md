# Goal Parser Demo V1 范围与开发说明

状态：已确认首版范围；待实现、待验证

创建日期：2026-09-21

> 当前 Demo 仅交付一次 Goal 分析、机会发现、圈客和策略执行，不构建 Replan。Parser 澄清后结束本次运行；补全后重新提交完整请求，创建独立 Goal/运行，不续接旧计划或产物。以 AGENTS.md 的当前 Demo 范围为准。

## 1. 使用方式与优先级

本文是 Goal Parser 首版的实施依据，目标是尽快恢复自然语言到结构化 Goal 的基本链路，让后续业务能力可以接入。本文只交付 Parser 及其 BusinessAgent 门禁，不代表完整经营 Demo 已完成。

用户已明确同意缩小首版范围，并要求提供可供后续模型直接执行的开发文档。因此本文包含具体协议、文件范围、任务顺序和测试要求。

对于首版范围，本文取代 `2026-09-21-goal-parser-convergence.md` 中要求完整落地的通用修订、细粒度恢复和两步迁移安排。原文保留为后续设计参考。项目级可信来源、规则执行和 Domain 边界仍然有效。

后续开发者先读 AGENTS.md 和当前事实文档，再读本文。事实文档与工作区不一致时，以核实的代码为准。不要因原方案标为“已确认”而补做本文明确延后的功能。

## 2. 开始前的工作区事实

2026-09-21 编写本文时只做了文件检查，没有运行测试：

- `src/application/goal_parser/__init__.py` 为空。
- 原 `goal_parser.py`、`metric_vocabulary.json` 和 `tests/application/test_goal_parser_contracts.py` 在工作区中处于删除状态。
- `src/application/__init__.py` 和 `business_agent.py` 仍导入 Parser 符号。
- Planner 实际位于 `src/application/planner/`；执行相关组件位于 `src/application/capability/`。
- 当前代码使用 `src.domain`、`src.model` 等导入路径。
- Domain 已有 Goal、MissingInformation 和不可变 `Goal.revise()`，无需新建替代对象。

这些是编写时快照，不是允许覆盖用户后续修改的指令。实施前重新检查 `git status --short`。不得重置工作区或恢复整份旧实现；按本文构建首版。文档曾记载的 19 项通过不能充当新实现验收结果。

## 3. 首版交付范围

### 3.1 必须完成

1. 单次完整自然语言请求生成 Goal。
2. 支持量化经营目标和探索经营机会两类入口。
3. 提取指标、目标值、时间原文、产品、需求、客群及约束。
4. actor/channel 来自可信 RuntimeContext；模型不能决定身份。
5. 指标来自小型版本化 JSON 配置；金额由代码进行有限格式规范化。
6. 关键信息缺失返回结构化 MissingInformation，并阻止 Planner 调用。
7. 可选信息未提供时保持空值，不追问、不补造。
8. 模型失败、协议失败有稳定错误码和安全提示。
9. 离线契约测试及 BusinessAgent 门禁测试。

### 3.2 明确不做

- 自然语言局部修订、KEEP/SET/CLEAR、集合增删和修改冲突合并。
- 自动把澄清回答与旧目标拼接、会话恢复、Goal 持久化。
- 自动 JSON 修复、语义重试、模型降级、跨模型评测平台。
- 逐字段部分接受与恢复、来源证据图、复杂置信度判断。
- 日期计算、自然语言数学计算、多指标目标、子目标分解。
- 指标服务端口、词汇注册中心、动态插件和额外工作流。
- 客户归属、产品适配、分发权限等业务裁决。
- HTTP API、前端、Planner/Replan 重构或完整经营能力实现。

这些限制必须在结果和文档中诚实体现，不能靠模型“尽量处理”暗中扩大范围。

## 4. 用户体验与验收示例

| 用户请求 | 首版结果 |
| --- | --- |
| 开门红目标500W NBEV，主推御享分红26和御享金越年金 | 创建量化 Goal；时间保留“开门红”；产品为用户提及，不代表适配结论 |
| 这个月业绩做到500W | 返回带目标值、时间和指标缺失的部分 Goal，要求重新提交包含具体指标的完整目标 |
| 帮我发现近期经营机会 | 创建探索 Goal；金额、指标和产品可以为空 |
| 下半年目标300万元NBEV，主推产品甲 | 不改 Parser 代码即可解析；不校验产品甲是否真实在售 |
| 改成400W / 去掉第二个产品 | 要求重新提交完整目标，不推测修改对象 |
| 目标100件保单 | 当前词汇未配置该指标时要求澄清，不创造 metric code |
| 给客户张三直接发消息 | 当前首版入口不支持该意图；要求说明经营目标，不直接执行 |

澄清提示统一说明“请补全后重新提交完整目标”。重新提交作为新请求生成新 ID；不声称是旧 Goal 的续接或修订。

## 5. 公共接口与输出

### 5.1 公共入口

继续使用 `src.application.goal_parser`，导出：

- `GoalParser`
- `GoalParseResult`
- `GoalParseStatus`
- `RuntimeContext`
- `MetricVocabulary`（只做本地配置加载和查询的普通类，兼容当前 Application 导入，不定义额外 Protocol）

构造接口采用 `GoalParser(model=..., model_name=..., goal_id_factory=None, metric_vocabulary=None)`。默认 ID 由 uuid 生成；测试可注入固定 ID；配置默认从包内文件按 `__file__` 定位读取，不依赖运行目录。

解析保持异步：`parse(user_request=..., runtime_context=None, existing_goal=None)`。

`existing_goal` 仅保留调用兼容性：只要非空，立即返回澄清，提示首版不支持修改、请以新请求重新提交完整目标。不调用模型、不调用 revise、不修改或返回旧 Goal，不分配新 ID。客户端须在重新提交时不携带 existing_goal。

RuntimeContext 包含 `actor_id`、`channel_id`、`context_source`。三项均为非空字符串才有效。Demo 调用入口显式传入模拟身份，来源标记为 `demo_runtime`；Parser 中不硬编码代理人或个险默认值。缺失上下文时返回技术失败 `RUNTIME_CONTEXT_REQUIRED`，因为这是调用配置问题，不应让用户通过自然语言提供可信身份。

### 5.2 结果契约

状态只使用 `SUCCESS`、`CLARIFICATION_REQUIRED`、`TECHNICAL_FAILURE`。

结果字段固定为：

| 字段 | 规则 |
| --- | --- |
| status | 上述三种状态之一 |
| goal | 成功必有；缺失澄清可有；技术失败或不支持修订时为空 |
| missing_information | MissingInformation 的不可变集合，默认空 |
| clarification_question | 澄清时必填，其他情况为空 |
| error | 技术失败时稳定错误码，其他情况为空 |
| diagnostics | 普通字典，首版只记录词汇 source_id/version；不放原始异常或客户数据 |
| need_clarification | 由 status 推导的属性，不能独立存储另一份布尔状态 |

存在 Goal 时，结果 missing_information 直接使用 Goal 中同一组信息。技术失败不伪装成用户信息缺失。

## 6. 模型输出协议

每次正常请求只调用一次现有 `ChatModel.complete()`。不新增模型 SDK。system 消息描述协议与约束，user 消息仅包含用户请求；不发送 RuntimeContext 或 existing_goal。词汇配置作为受控 system 上下文提供 code 以外的展示名与别名即可。

模型输出一个 JSON 对象，全部键必须存在，不允许额外键：

```json
{
  "goal_type": "performance_achievement",
  "metric_text": "NBEV",
  "target_text": "500W",
  "time_text": "开门红",
  "products": ["御享分红26", "御享金越年金"],
  "needs": [],
  "audience_text": null,
  "constraints": []
}
```

- `goal_type` 只接受 `performance_achievement`、`opportunity_discovery` 或 null。它是应用支持范围，不是业务事实配置。
- metric_text、target_text、time_text、audience_text 为非空字符串或 null。
- products、needs、constraints 为非空字符串数组，可为空数组。
- 除 goal_type 外，所有字符串必须逐字摘自本次用户输入，不改写、不补全、不推理。
- 未表达的字符串字段为 null，数组为 []。
- 修改请求、无法理解或超出两类入口范围时 goal_type 为 null。
- 只接受一个指标和一个目标值；多指标、多目标或相互冲突的目标由模型返回 goal_type=null，要求用户拆成单一目标。首版不承诺确定性识别所有自然语言多目标表达。
- 不允许输出 metric code、actor、channel、日期范围、权限或业务规则结论。

Prompt 的指令文本不能混入用户消息。不要把业务示例产品当作默认候选。测试必须包含替换产品与阶段的输入。

## 7. 确定性处理规则

按以下顺序执行，不自行增加恢复路径。

### 7.1 前置检查与协议检查

1. 检查 RuntimeContext；不合法返回技术失败。
2. existing_goal 非空时返回不支持修订的澄清。
3. 空白请求返回缺少 goal_type 的澄清，不调用模型。
4. 调用模型一次。调用异常返回 `MODEL_CALL_FAILED`。
5. 读取非空文本并 `json.loads`；非 JSON、Markdown 围栏、额外前后文字、非对象、字段错误或类型错误均返回 `MODEL_PROTOCOL_INVALID`。不自动修复。
6. 检查原文依据：所有非空文本和数组元素必须是用户请求的连续子串（strip 后匹配，不做同义词推理）。任一字段无依据，整体返回 `MODEL_GROUNDING_FAILED`，不创建 Goal。此简化有意替代原方案的逐字段过滤。

这只能证明文本出现过，不能证明理解了否定、指代和语义关联。Prompt 必须排除被用户否定的产品；真实模型冒烟需覆盖否定句。不得宣称首版已解决完整语义真实性校验。

### 7.2 指标配置

配置结构使用 source_id、version、metrics 数组。每项包含 code、display_name、aliases、unit。初始只配置 NBEV，code 统一为 `nbev`，别名含 `NBEV`，规范单位为“元”。其他别名仅在有明确业务依据后添加，不能把“业绩”映射为 NBEV。

对 metric_text 做 strip 和 casefold 后与配置名称/别名全等匹配。零命中或多个不同 code 命中均视为指标缺失。不要对整段请求做模糊扫描或从模型接收 code。

配置不存在、字段不合法、source_id/version 为空等视为 `METRIC_CONFIG_INVALID`；禁止静默回落硬编码词汇。词汇版本进入 diagnostics，不改 Domain Metric。

### 7.3 目标值

只支持正的阿拉伯数字（可含小数）加可选单位，单位范围：无单位、元、万、万元、W/w、亿、亿元。可忽略数字与单位之间空格，不支持千分位、中文数字、区间、算式或复合金额。

使用 Decimal 转换；W/w、万、万元乘以 10000，亿、亿元乘以 100000000，统一保存为元。因此 `500W` 是 `Target(Decimal("5000000"), "元", "at_least")`。不要同时保存 5000000 和“万”。

只有指标配置声明货币单位为“元”时才应用此规则，无单位目标值也按该配置单位理解。未识别指标时，显式金额单位可构造 Target；无单位数字不猜单位，保留 target 缺失。

首版只支持正向达成目标（at_least）。负数、零、金额范围、“最多/不超过”等其他比较意图均要求澄清；不能去掉修饰词后按正向目标解析。Prompt 应让 target_text 包含比较修饰词，从而交给上述有限格式校验拒绝。该语义提取依赖模型，列为真实模型验证项。

格式不支持属于用户表达超出支持范围，返回 target 的 MissingInformation，不是技术失败。不要为了通过测试不断增加自然语言正则分支。

### 7.4 Goal 映射

- goal_type=null：返回 goal_type 缺失的澄清，不创建 Goal。
- ID 由应用生成，version=1，original_request 保留完整首次输入。
- TimeHorizon 仅设置 raw_expression；start_at/end_at 均为空。
- ProductOrNeedContext 仅保存提取的 products/needs；两者均为空时整个字段为空。
- AudienceScope 有原文时使用 scope_type=`user_expression`、raw_expression=原文，scope_reference 为空。不能把人名或客群文本编造成客户 ID。
- 每条约束映射 Constraint(code=`user_stated`, description=原文, source=`user_request`)。允许同 code 多条；它不是规则裁决结果。
- ChannelAndActor 从 RuntimeContext 构造；assumptions 始终为空。
- 量化 Goal 要求合法 metric 和 target。任一缺失均生成 required_before_execution=true 的 MissingInformation。
- 探索 Goal 可无 metric/target；但用户明确提供了指标或目标值且无法规范化时仍要求澄清，不能静默丢掉明确约束。
- 时间、产品、需求、客群和约束未提供不产生阻塞。
- 所有缺失项都填写 field、reason、impact；不依赖自由文本作为唯一缺失事实源。
- 有阻塞缺失时可返回上述部分 Goal，但状态必须为 CLARIFICATION_REQUIRED；无缺失返回 SUCCESS。

## 8. BusinessAgent 接入边界

复用当前 parse 调用，不重写执行循环。

1. TECHNICAL_FAILURE → BusinessAgent FAILED，不调用 Planner；error 只传稳定错误码。
2. need_clarification 或结果/Goal 中任意 required_before_execution=true → CLARIFICATION_REQUIRED，不调用 Planner。
3. 只有 SUCCESS 且 goal 非空、没有阻塞项才调用 Planner。
4. 其他自相矛盾结果 → FAILED，不调用 Planner。

原文中关于外部写操作的权限、客户归属和产品适配门禁没有取消，而是留在实际业务 Tool 执行前实现。本轮不新增写操作，也不能把 Parser 成功当成可经营授权。

## 9. 文件范围与任务顺序

建议只新增或修改以下位置：

| 文件 | 职责 |
| --- | --- |
| src/application/goal_parser/__init__.py | 公共导出，无业务逻辑 |
| src/application/goal_parser/goal_parser.py | 结果与上下文类型、模型调用、检查、Goal 构造、轻量 MetricVocabulary |
| src/application/goal_parser/prompts.py | 协议和提取规则 |
| src/application/goal_parser/metric_vocabulary.json | 版本化指标配置 |
| src/application/business_agent.py | 只加强解析结果与阻塞门禁 |
| tests/application/test_goal_parser_contracts.py | Parser 离线契约测试 |
| tests/application/test_business_agent_goal_gate.py | Planner 不被误调用的测试 |

不要求继续拆分更多文件，不新增依赖。`src/application/__init__.py` 只在导出确需调整时修改。Domain、Model、Planner、Capability、Web 不在本轮实现范围。

按顺序完成：

1. **恢复导入和协议**：实现公共符号、结果类型、本地词汇加载；验证 `import src.application` 成功。
2. **实现一次提取**：模型请求、严格结构与原文检查、异常分类；用 FakeChatModel 验证只调用一次且不泄露 RuntimeContext。
3. **实现规范化和 Goal 构造**：按第 7 节逐条实现，不扩大数字、时间和修改语义。
4. **接入门禁**：在 BusinessAgent 中覆盖澄清、失败、矛盾结果；用 spy/stub 确认 Planner 调用次数。
5. **完成测试和事实文档同步**：记录真实检查结果和未验证项。

每步先做到对应测试可验证，再继续。不要先构建通用框架，不需要形式上的“先等价迁移旧实现”。如果发现非本轮改动导致的其他失败，记录原因，避免趁机重构整个应用。

## 10. 最小测试矩阵

使用标准库 unittest、现有 FakeChatModel 和 OpenAI ChatCompletion 测试响应。测试从可观察行为断言，不锁定私有函数组织。

| 编号 | 输入/条件 | 必须断言 |
| --- | --- | --- |
| T01 | 完整500W NBEV请求 | 金额5000000元、nbev、version=1、原文、产品和时间正确 |
| T02 | 换阶段、产品、金额 | 无需修改 Parser 即生成对应字段 |
| T03 | 只有探索意图 | SUCCESS；无指标、金额和产品也可继续 |
| T04 | 500W业绩 | 部分 Goal；metric 缺失且阻塞；Planner调用0次 |
| T05 | 未配置/歧义指标 | 不生成模型臆造code，返回结构化澄清 |
| T06 | 数值参数化 | 500W、500万元、0.05亿元均为5000000元；零、负数、区间、不超过表达拒绝 |
| T07 | 模型臆造产品或日期 | MODEL_GROUNDING_FAILED；Goal为空；Planner调用0次 |
| T08 | 模型输出额外actor/channel/code | 协议失败；不可覆盖身份 |
| T09 | RuntimeContext | 缺失时模型调用0次；有效时Goal带可信来源；模型消息不含身份值 |
| T10 | malformed JSON/错误类型/缺键/空响应 | MODEL_PROTOCOL_INVALID；模型调用1次，无修复 |
| T11 | 模型调用抛异常 | MODEL_CALL_FAILED；不暴露异常文本 |
| T12 | existing_goal非空 | 澄清；模型调用0次；旧Goal不变；不创建新版本 |
| T13 | 空请求/goal_type=null | 澄清且无Goal，不用占位goal_type |
| T14 | 可构造部分Goal | 结果与Goal的missing_information一致 |
| T15 | BusinessAgent矛盾结果 | SUCCESS但阻塞/无Goal不进入Planner |
| T16 | 配置损坏/版本缺失 | METRIC_CONFIG_INVALID；不存在硬编码降级 |
| T17 | 正常BusinessAgent入口 | Planner收到当前Goal；沿用已有执行链，不要求真实业务Tool |

FakeModel 测试证明代码处理协议的行为，不能证明真实模型自然语言理解准确。

## 11. 验证命令与完成标准

从仓库根目录使用 PowerShell。当前源码以 `src.*` 导入，先用实际导入验证，不能直接照抄过期文档里的导入方式：

```powershell
.\.venv\Scripts\python.exe -c "import src.application; print('application import ok')"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

解释器路径若不存在，先确认项目已有 Python 环境，不擅自安装新工具。离线验证完成后，如已配置真实模型，可用合成请求执行少量冒烟：完整目标、含糊指标、探索请求、否定产品、比较词、多目标、局部修改。不得输出配置密钥；没有模型配置时明确记录“未执行真实模型验证”，不以离线测试替代。

完成标准：

- 公共导入可用，上述测试矩阵通过，测试覆盖失败不进入 Planner。
- 单次正常解析只调用一次模型，首版不支持项不会被静默当作已支持。
- 没有示例产品/经营阶段/代理人硬编码，没有新增依赖或 Domain 改动。
- `doc/current-state.md` 直接更新为真实首版能力和限制，移除与当前实现矛盾的 KEEP/SET/CLEAR、单次修复等描述。
- `doc/architecture.md` 校准实际目录、入口和依赖；不把未来设计写成当前实现。
- `dev-log.md` 在 Unreleased 记录实现与实际验证结果，不复用历史测试数量。
- 最终交付列出改动、测试结果、已知限制；业务 Tool、API 和前端未接通时不得宣称完整 Demo 可运行。

## 12. 可复制给开发模型的任务

> 请按 `doc/design/2026-09-21-goal-parser-demo-v1.md` 实现 Goal Parser Demo V1。先读取项目 AGENTS.md 与当前事实文档，再检查工作区，保护已有修改。本文是首版实施依据，原 goal-parser-convergence 中通用修订、自动修复、细粒度字段恢复和两步迁移要求已延后。严格遵循本文协议、处理顺序、文件范围和测试矩阵；不扩展功能、不新增框架或依赖、不修改 Domain/Planner/Capability/Web。完成公共导入、一次模型提取、确定性规范化、BusinessAgent 门禁与离线测试，最后同步当前状态、架构和开发日志。真实模型未验证时明确说明。遇到文档未覆盖且会改变公开契约的问题先说明，不自行设计第二套协议。
