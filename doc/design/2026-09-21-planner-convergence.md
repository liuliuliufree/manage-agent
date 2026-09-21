# Planner 收敛设计

状态：已确认

## 1. 文档定位

本文确认首次规划阶段的 Planner 职责、输入输出语义、Capability 可见信息、Planning Context、Plan 构造与校验边界，为后续独立开发会话提供连续的设计上下文。

本文是已确认设计，但不覆盖当前代码、`doc/current-state.md`、`doc/architecture.md` 或 M1 Domain Contract；在对应代码完成并验证前，不得把本文描述为当前实现事实。本文只确认首次规划以及首次规划与 Replan 共用的基础，Replan 的完整触发矩阵、成功结果保留、Plan 换版和恢复上限另行收敛。

## 2. 当前事实

当前 Planner 位于单一 Application 模块中，已经具备以下能力：

- 接收 Goal、简单 Existing Context 和 Capability Catalog；
- 使用 `ChatModel` 动态选择完成当前请求所需的最少合理 Capability；
- 允许跳过、重复和重排 Capability；
- 使用 `depends_on` 表达步骤依赖；
- 由 Application 生成 Plan ID、版本、GoalRef 和初始状态；
- 确定性拒绝 Catalog 外能力、重复 step ID、未知依赖和依赖环；
- 对非法 JSON 最多执行一次只修复格式的模型调用；
- 使用同一个 Planner 的另一入口处理当前最小 Replan。

当前模块同时承担首次规划 Prompt、Replan Prompt、模型调用、JSON 修复、模型输出解析、Plan 构造和 Replan 构造，职责已经开始集中。

当前已知缺口包括：

- 模型直接生成正式 `step_id`，而 step ID 又是执行结果和 Replan 关联键；
- Capability Catalog 只有描述，不能表达版本、可用性、输入输出边界和副作用；
- Catalog 与执行 handler 映射分离，但 Planner 不知道 Capability 是否真的可执行；
- Existing Context 是松散引用字典，缺少稳定类型、有效性和 Goal 关联语义；
- `depends_on` 只表达执行顺序，不保证前序产物进入后继 CapabilityRequest；
- 结构合法性校验不能发现输入无来源、Capability 不可用或写操作控制缺失；
- Planner 不能区分无需行动、信息不足、不支持和技术失败；
- BusinessAgent 完成或停止后，Plan 生命周期状态不会同步转换；
- 当前没有真实 Capability 数据流证明后继步骤能够消费前序输出。

## 3. 目标与非目标

### 3.1 目标

- 保留模型根据 Goal 和 Context 动态选择、跳过、重复和重排 Capability 的能力。
- 将模型生成的规划意图与正式 Plan 身份、版本和运行关联键分开。
- 让 Application 确定性掌握 Capability 可用性、输入来源、控制策略和 Plan 合法性。
- 让 Planner 能明确表达计划就绪、信息不足、当前不支持、无需行动和技术失败。
- 收敛 Planner 可见的 Context 和 Capability 信息，避免继续传入开放式字典或只有自然语言描述的 Catalog。
- 保持 M1 PlanStep 的轻量边界，不把 Plan 扩张成 Workflow DSL。
- 为后续 Replan 复用同一套 Planning Context、Capability View、Plan 构造和校验基础。
- 保持一个稳定的 Planner 公共入口，同时拆分内部职责。

### 3.2 非目标

- 不在本文中确认 Replan 的完整触发矩阵和恢复策略。
- 不实现 Retry、Fallback、循环、条件分支或并行调度引擎。
- 不把 Tool 参数、客户事实、Prompt 或任意业务 payload 写入 PlanStep。
- 不让 Planner 判断客户归属、经营权限或规则例外。
- 不建设通用 Workflow Engine、Planning DSL 或候选 Plan 搜索框架。
- 不为每个场景建立独立 Planner。
- 不在 Planner 内执行 Capability 或维护第二套步骤运行状态。
- 不提前确定完整的生产级 Capability 元数据 Schema。

## 4. 核心职责边界

Planner 的处理过程分为三个阶段：

```text
Goal + Planning Context + 当前 Capability View
                      ↓
模型生成规划意图
                      ↓
确定性规范化、可执行性校验和身份分配
                      ↓
正式 Plan 或明确的规划结果
```

### 4.1 模型职责

模型负责：

- 根据 Goal 和现有 Context 选择必要 Capability；
- 判断哪些已有产物可以省略前置能力；
- 提出步骤之间真实必要的控制依赖；
- 提出可以独立进行的步骤；
- 在完成 Goal 所需时重复使用同一 Capability；
- 避免机械补齐全部能力。

模型不得决定：

- Plan ID、Plan 版本和 GoalRef；
- 正式运行 step ID；
- Capability 是否真正可用；
- 外部写操作是否可以绕过规则校验或用户确认；
- Plan 生命周期状态；
- Retry、循环、条件 DSL 或底层 Tool；
- Catalog 外不存在的能力。

### 4.2 Application 职责

Application 负责：

- 构造最小且受控的 Planning Context；
- 构造 Planner 当前可见的 Capability View；
- 校验模型规划意图的结构和引用；
- 分配正式 Plan 和步骤身份；
- 检查 Capability 可用性和输入来源；
- 检查不可绕过的写操作控制策略；
- 构造 M1 Plan；
- 区分无需行动、信息不足、不支持和技术失败；
- 保证 Planner 输出不能降低确定性业务控制。

### 4.3 Domain 职责

M1 Plan Contract 继续表达针对明确 Goal 版本的当前行动意图。PlanStep 只选择 Capability 并表达控制依赖。Planning Context、模型草案、Capability View 和规划结果属于 Application 的临时契约，不成为第二套 Plan 领域对象。

## 5. 规划结果

Planner 统一返回 Application 层规划结果，并明确区分以下结果：

| 结果                     | 含义                                  | 后续动作                 |
| ------------------------ | ------------------------------------- | ------------------------ |
| `PLAN_READY`           | 已形成合法且当前可执行的 Plan         | 创建 ExecutionContext    |
| `INFORMATION_REQUIRED` | 结合能力边界后发现阻塞性信息缺失      | 询问用户，不执行 Plan    |
| `UNSUPPORTED`          | 当前可用 Capability 无法完成 Goal     | 返回能力缺口，不创造能力 |
| `NO_ACTION_REQUIRED`   | 当前 Goal 已满足或无需执行 Capability | 正常结束                 |
| `FAILED`               | 模型协议或内部技术失败                | 进入技术失败处理         |

`INFORMATION_REQUIRED` 不替代 Goal Parser。只有必须结合 Capability 输入边界或当前可用性才能发现，且缺失会导致明显不同的行动、越权或不可逆执行时，才属于 Planner 阶段。缺失项必须能对应 Capability View 中的必需输入或控制要求，不能仅凭模型偏好扩大澄清范围。

这些结果实现为统一的 Application 层契约。只有 `PLAN_READY` 携带正式 Plan；其他结果携带与其状态相符的结构化原因、缺失项或能力缺口。首版不允许零步骤 Plan。

模型可以提出规划结果意图，但最终状态由 Application 校验后构造，不能直接信任模型枚举值：

- `PLAN_READY` 必须通过结构和可执行性校验；
- `INFORMATION_REQUIRED` 必须能映射到必需输入或可信控制策略的阻塞性缺失；
- `UNSUPPORTED` 必须指出 Capability View 中真实存在的能力缺口，且不能把可补充信息或一次草案校验失败包装为不支持；
- `NO_ACTION_REQUIRED` 必须引用 Planning Context 中足以支持当前 Goal 已满足或无需行动的有效产物；
- 解析、模型协议、校验重试耗尽或内部技术问题收敛为 `FAILED`。

## 6. 模型规划意图与正式 Plan

### 6.1 规划意图

模型输出应被视为规划草案，而不是正式 Plan。草案表达：

- 本次规划内的临时步骤别名；
- 选择的 Capability ID；
- 对其他临时步骤的依赖。

临时步骤别名只用于解析模型输出和依赖关系，不直接承担跨版本运行身份。

### 6.2 正式步骤身份

正式 step ID 由 Application 分配，而不是交给模型。

这样可以分开：

- 模型用于表达规划结构的可读别名；
- ExecutionContext、CapabilityResult 和 Replan 使用的稳定运行身份。

临时步骤别名只在单次模型草案内唯一，用于解析依赖；Application 在校验草案后一次性分配不带业务顺序含义的正式 step ID，并将别名依赖规范化为正式依赖。Replan 如何引用保留的旧 step ID、如何为新步骤生成身份，将在 Replan 设计中进一步确认。

### 6.3 正式 Plan

Application 校验草案后构造 M1 Plan，并负责：

- Plan ID；
- 初始版本；
- GoalRef；
- 初始生命周期状态；
- 正式 step ID；
- 规范化依赖。

模型不得通过输出覆盖这些字段。

## 7. Planning Context

不再把任意字典直接作为 Planner Context。受控 Planning Context 至少表达：

```text
Planning Context
├── 绑定的当前 GoalRef
├── 当前可用对象引用及类型
├── 已知缺失信息
└── 规划基准时间
```

Planner 需要知道当前已经具备哪些可用产物、它们属于什么类型、是否仍有效以及能否作为 Capability 输入。每个可用产物引用至少具有稳定引用、产物类型、有效性结论和来源，并在业务产物需要时关联具体 Goal 版本。Planner 不需要读取完整客户画像、Opportunity 载荷或内部规则对象。

Planning Context 属于 Application 的受控只读视图，不取代 ExecutionContext，也不复制完整业务事实。

已确认以下语义：

- 引用通过 Application 层的类型化产物引用表达，不再依赖 `*_refs` 键名推断类型；具体类名和字段在实现时按最小消费者确定。
- Planning Context 必须绑定当前 GoalRef，但不重复保存 Planner 已单独接收的完整 Goal；当前 Goal 产生的业务产物必须关联具体 Goal 版本。复用其他 Goal 的产物必须由 Context 构造职责确认类型兼容、仍然有效且允许跨 Goal 复用，模型不能自行认定。
- 引用有效性由 Application 的 Context 构造职责根据权威来源、有效期和规划基准时间判定；模型只消费判定后的只读视图。
- CapabilityResult 的输出只有在成功或部分成功、通过受控产物提取并形成稳定引用后，才可进入后续 Planning Context；不得把任意输出 payload 自动并入 Context。
- 规划基准时间是首版必需字段，由 Application 注入并用于有效性判定，模型不得生成或覆盖。

## 8. Planner 可见的 Capability View

Capability Catalog 与执行 handler 映射继续保持分离，但 Planner 需要知道当前哪些能力可以规划。

Application 层 Capability View 至少包含：

- 稳定 Capability ID；
- 名称、描述和版本；
- 当前可用性及其可信来源；
- 可执行实现是否就绪；
- 可接受的输入引用类型；
- 可能产生的输出引用类型；
- 是否可能改变外部状态；
- 不可绕过的控制策略引用；
- 必要的最小规划限制。

这些信息描述能力边界，不定义固定步骤顺序。不得把输入输出信息写成“某能力永远是第一步、某能力永远是第二步”。

首版先建立 Application 层 Planner View，不扩展 Domain `CapabilityDefinition`。只有字段语义经真实 Capability、执行和其他消费者共同验证后，才评审是否下沉为稳定 Domain 契约。本文确认语义边界，不预先锁定最终类名或完整元数据 Schema。

## 9. Plan 校验

### 9.1 结构校验

继续保留当前确定性检查：

- Capability 属于当前 Catalog；
- step ID 唯一；
- 依赖目标存在；
- 步骤不能依赖自己；
- 依赖图不能成环。

### 9.2 可执行性校验

首版新增以下确定性最小检查：

- 所选 Capability 当前可用；
- 存在可执行实现，且实现就绪状态来自可信的注册或装配结果；
- 必需输入来自初始 Context，或可由依赖步骤产生；
- 后继步骤所需产物存在可追踪来源路径；
- 外部写操作绑定不可绕过的控制策略；
- 草案至少存在一个无需其他草案步骤即可满足输入的可执行起点；
- Application 构造的正式 Plan 与当前 GoalRef 一致。

必需输入来源检查以 Capability View 声明的引用类型为边界：输入必须来自 Planning Context 中已判定有效的产物，或来自当前草案中沿依赖路径可产生该类型的前序步骤。仅有 `depends_on` 而无匹配产物类型，或存在匹配产物但没有依赖路径，均不能视为输入可达。

外部写操作必须具有 Capability View 中来自可信执行策略的控制策略引用；模型添加的文字说明不能满足该检查。可执行性校验只阻止元数据能够确定的明显不可执行或越权草案，不负责评价模型选择的经营路径是否最优，也不搜索或证明所有可能方案。元数据尚未具备的语义必须明确标为未校验，不能通过 Demo 硬编码伪造完整校验能力。

### 9.3 修复边界

确认规则是：

- JSON 语法错误允许一次纯格式修复；
- 结构或可执行性错误不由代码静默改变模型方案；
- 首次草案校验失败时，允许把结构化错误代码、涉及的草案别名和允许的 Capability View 回传模型，执行一次受限语义重试；
- 语义重试必须作为独立模型调用记录原因和结果，不携带敏感内部信息，也不得改变 Goal、Context、Capability View 或控制策略；
- 第二次草案仍不合法时返回 `FAILED`，不再重试；模型或 Application 已能可靠证明能力集合不支持 Goal 时返回 `UNSUPPORTED`，不得把校验失败伪装成不支持；
- 不允许无限自修复、代码猜测性补边、替换 Capability 或其他不可观察的静默修改。

## 10. Plan 与数据流边界

M1 PlanStep 继续只包含 Capability 选择和控制依赖，不增加 Tool 参数、业务 payload、客户事实或通用输入映射。

确认的数据流边界是：

```text
Plan 控制依赖
        +
Capability 输入输出边界
        +
ExecutionContext 中的类型化产物引用
        ↓
后继 CapabilityRequest 的受控 input_refs
```

因此：

- Plan 表达“何时可以执行”；
- Capability 元数据表达“需要和产生什么”；
- ExecutionContext 保存“当前实际已经有什么”；
- CapabilityRequest 只携带本次调用需要的受控引用。

本文不锁定具体产物注册结构，但确认产物必须经受控提取形成稳定、类型化引用，且失败历史不能伪装为可复用产物。具体注册契约应在执行层产物回写实现前，结合真实 Capability 输出收敛。

## 11. Plan 生命周期边界

Planner 只负责创建初始 `ACTIVE` Plan，不根据模型文本设置生命周期状态。

生命周期转换由 Application 的执行协调职责确定性完成；在独立协调组件出现前可由当前 BusinessAgent 承担：

- 全部步骤成功后进入 `COMPLETED`；
- 确定性阻断导致整体无法继续时进入 `BLOCKED`；
- 新 Plan 版本生效后，旧版本进入 `SUPERSEDED`；
- 用户明确取消后进入 `CANCELLED`。

Capability 的单次失败不自动等于 Plan 生命周期失败。状态转换条件和历史保存方式不在 Planner 内部决定。

## 12. 无计划和无法规划

### 12.1 无需行动

当当前 Context 已经满足用户请求，或当前 Goal 不需要调用 Capability 时，不应强制模型生成无意义步骤，返回 `NO_ACTION_REQUIRED`。该结果必须说明理由，并引用 Planning Context 中支持“已满足”判断的有效产物；没有可验证依据时不能仅凭模型断言无需行动。

### 12.2 当前不支持

当当前 Capability 集无法完成 Goal 时，应返回 `UNSUPPORTED` 和能力缺口，不允许创造 Catalog 外能力。

### 12.3 需要信息

当缺失只能结合 Capability 输入边界确定时，可以返回 `INFORMATION_REQUIRED`。缺失应结构化表达，不能只返回自由文本错误。

无需行动场景不创建零步骤 Plan，由规划结果直接表达；这避免制造没有执行意图却参与 Plan 生命周期和审计的领域对象。

## 13. 内部组织方案

将当前单一 Planner 模块调整为 `src/application/planner/` 内部包，同时保持一个统一 Planner 公共入口。

内部职责至少分为：

- 服务编排和模型调用；
- Application 层规划草案与规划结果；
- 首次规划和 Replan Prompt；
- Planning Context 构造；
- 结构及可执行性校验；
- 正式 Plan 构造。

具体文件名和数量在实现时根据现有代码确定。不得把拆包演变成 PlannerAgent、ReplannerAgent、场景 Planner 或 Planning Framework。

公共导入路径必须保持兼容，现有调用方不应因为内部拆包而被迫感知实现结构。内部拆包先作为不改变外部行为的等价重构单独完成，通过现有测试后再引入规划结果等行为变化。

## 14. 迁移原则

推荐分阶段实施并分别验证：

1. 先进行 Planner 内部职责拆分，保持现有外部行为和公共导入兼容；
2. 再引入规划结果与模型草案边界；
3. 收敛 Planning Context 和 Capability View；
4. 在真实元数据基础上增加最小可执行性校验；
5. 最后调整执行层的产物引用回写和 Plan 生命周期转换。

结构调整、行为变化和数据流变化应避免混在一个不可区分的变更中。迁移期间不得创建第二套 Plan 或把 PlanStep 扩张为 Workflow DSL。

行为变化后需要同步检查：

- `doc/current-state.md` 中 Planner 当前能力和限制；
- `doc/architecture.md` 中目录、职责和数据流；
- `dev-log.md` 中功能变更和验证结论。

## 15. 验收场景

后续实现至少应覆盖以下行为：

1. 只需要一个 Capability 的 Plan。
2. 已有 Opportunity 时跳过洞察。
3. 已有 Customer 时直接生成策略。
4. 同一 Capability 在一个 Plan 中重复出现。
5. 两个无依赖步骤能够表达为并列 Ready。
6. Catalog 外 Capability 被拒绝。
7. 当前不可用的 Capability 不能进入正式 Plan。
8. 没有可执行实现的 Capability 不能进入正式 Plan。
9. 后继步骤的必需输入能由 Context 或依赖步骤产生。
10. 没有输入来源的 Plan 被拒绝。
11. 外部写操作不能省略可信控制策略。
12. 模型不能决定 Plan ID、Plan 版本、GoalRef 和正式 step ID。
13. JSON 格式错误最多修复一次。
14. 结构合法但不可执行的草案不会静默成为正式 Plan。
15. 当前 Goal 已满足时能够表达无需行动。
16. 当前能力无法支持 Goal 时能够表达不支持。
17. 非 Demo 产品和非开门红场景继续复用同一 Planner。
18. 公共导入和 BusinessAgent 调用边界保持兼容，或提供明确迁移说明。
19. 首次草案结构或可执行性失败时最多进行一次可观察的语义重试，重试耗尽后不会继续调用模型。

## 16. 风险与取舍

- Application 分配正式 step ID 可以稳定运行关联，但会增加模型草案到正式 Plan 的映射过程。
- Capability View 太弱无法校验可执行性，太强则可能提前建设复杂元数据体系。
- Planning Context 收敛能够减少任意数据泄漏，但需要明确产物引用的类型和有效性来源。
- 输入输出边界可以帮助 Planner 形成可执行计划，但不得退化为固定能力顺序。
- 增加规划结果能够区分业务情况，但会改变 BusinessAgent 当前只接收 Plan 或异常的调用方式。
- 可执行性校验依赖真实 Capability 元数据；在元数据尚不存在时不应通过硬编码 Demo 流程伪造校验能力。
- 允许语义修复可能提升模型容错率，也可能形成不可观察的反复规划；首版应保持严格上限。

## 17. 已确认事项

* 本轮只收敛首次规划；Planning Context、Capability View、草案、正式 Plan 构造和校验作为首次规划与 Replan 的共享基础。
* 模型只生成临时步骤别名，正式 step ID 由 Application 分配。
* Planner 返回统一的 Application 层规划结果，并区分 `PLAN_READY`、`INFORMATION_REQUIRED`、`UNSUPPORTED`、`NO_ACTION_REQUIRED` 和 `FAILED`。
* 无需行动时不创建空 Plan；只有 `PLAN_READY` 携带正式 Plan。
* Existing Context 升级为受控、只读的 Planning Context；每次规划必须具有由 Application 注入的规划基准时间。
* Planner 使用 Application 层 Capability View；首版不扩展 Domain `CapabilityDefinition`。
* Capability View 最小覆盖版本、当前可用性、可执行实现状态、输入输出引用类型、副作用分类和不可绕过的控制策略引用。
* 首版可执行性校验只验证元数据能够确定的可用性、实现、输入来源、产物路径、写操作控制、可执行起点和 Goal 关联，不评价经营路径是否最优。
* JSON 语法错误保留一次纯格式修复；结构或可执行性失败允许一次可观察的受限语义重试，失败后停止，不做静默改写或循环修复。
* Plan 生命周期由 Application 的执行协调职责统一转换；当前可暂由 BusinessAgent 承担，Planner 不改变生命周期。
* Planner 内部拆包先作为保持外部行为和公共导入兼容的等价重构单独完成。
* 产物引用的有效性和 Goal 关联由 Application 的 Context 构造职责判定；Capability 成功输出经受控提取后才可进入后续 Context，不能自动合并任意 payload。

## 17.1 留待后续设计的问题

以下内容不阻塞首次规划实施，但必须在相应阶段前收敛：

- Replan 的完整触发矩阵、恢复上限、旧步骤身份保留和版本历史保存；
- 类型化产物引用与产物注册的具体 Application 契约；
- 真实写 Capability 的控制策略表达和用户确认状态；
- 多个可执行起点的串行选择、未来并行执行与调度策略；
- 规划结果面向 API 和前端的展示契约。

## 18. 成功标准

- 新会话只阅读当前事实源、M1 Contract 和本文即可理解 Planner 的问题、边界和已确认方向。
- 模型规划意图与正式 Plan 身份、版本和运行关联键具有清晰边界。
- Planner 不会选择不存在或当前不可用的 Capability。
- 已有 Context 能够可靠跳过无意义前置步骤，后继输入具有可追踪来源。
- 结构合法但实际不可执行或越权的草案不会进入执行。
- Plan 保持轻量，不包含 Tool 参数、业务事实或 Workflow DSL。
- 无需行动、信息不足、不支持和技术失败不会继续混为异常。
- 内部代码不再集中于单一大文件，同时公共 Planner 入口保持稳定。
- 首次规划与后续 Replan 可以复用同一套 Context、Capability View、Plan 构造和校验基础。
