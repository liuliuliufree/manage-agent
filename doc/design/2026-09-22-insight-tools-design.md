# M4 通用只读工具设计

状态：设计稿；按用户要求细化通用 Tool 的职责和协议，尚未实现

## 1. 设计结论

首版建设三个只读工具：**search_knowledge、read_knowledge、aggregate_records**。它们分别检索资料、读取原文、统计结构化记录，不生成经营机会或客户推荐。

通用性指换产品、经营阶段、主题或数据快照后继续使用同一协议，而不是立即建设任意数据源查询平台。首版实现仅支持本地 Markdown 和本地合成客户/行为数据；以后可替换数据适配实现，无需主 Agent 理解文件结构。

工具不得包含“养老机会”“开门红圈客”“500W拆解”等专用入口，不内置产品名判断分支，不读取设计文档中的预期统计作为结果。

本文件补充 M4 和 Mock 数据设计，不扩大单次 Plan 的 Demo 范围，不构建 Replan、不实现圈客或策略执行。下述协议用于收敛设计；本次只写文档，具体实现完成前不得描述为已有工具。

## 2. Capability 与 Tool 的边界

| 职责 | 承担者 |
| --- | --- |
| 解析本次经营目标、选择定向洞察能力 | 已有 Parser/Planner |
| 查找产品资料、引用真实章节 | 知识工具 |
| 计算客户规模、年龄及行为分布 | 统计工具 |
| 判断哪些证据支持某个机会、比较优先性 | directional_insight Capability |
| 生成正式 Opportunity、关联证据并发布引用 | Capability 与 Application |
| 选择具体客户及逐人经营策略 | 后续 M5 能力，不在本工具范围 |

工具给出“主题A有多少咨询”“这段条款写了什么”，不输出“主题A应优先经营”“客户适合买某产品”。Capability 可以多次调用只读工具细化分析；这仍是一个 Plan 内同一步能力的执行，不是多轮计划。

是否由 LLM 选择工具或由确定性代码组合，是 Capability 内部尚待确认的选择。三个工具必须都可以独立测试和直接调用，不以新增 LLM/Agent Loop 为前置条件。

## 3. 复用现有协议与可信上下文

复用 `src/agent/tool.py` 的 Tool、parameters JSON Schema、validate_arguments 和 as_chat_completion_tool，不新增第二套 Tool 基类、插件注册中心或发现服务。工具定义在上层业务模块，不能把产品或客户逻辑放入 src/agent。

首版 handler 都是同步只读本地操作，与当前同步 CapabilityExecutor 相容；不要为此改成异步执行引擎。若由 Runtime 调用，遵守其既有校验和事件机制；若 Capability 直接调用，必须先使用同一个 validate_arguments，再执行 handler，并记录调用输入、结果状态及来源。不要因为直接调用而跳过校验，也不要另建通用调度器。

应用在装配时绑定以下可信内容，不作为模型可填写参数：

- 当前运行/请求标识、actor/channel、允许访问的数据集和文档集合。
- 本地资料根目录、快照时间、数据版本、产品目录与别名映射。
- 文件指纹、受控字段、主题代码、年龄分组配置和结果上限。

模型只能在已暴露的 opaque ID 和字段中查询，不能传文件路径、actor_id、channel_id、SQL、Python、任意表达式或新的数据源地址。Demo 数据全部属于个险/当前模拟代理人，装配时检查数据范围匹配即可，不建设多渠道过滤引擎；范围声明不能替代后续执行权限校验。

## 4. 共同返回结构

三个工具统一使用普通 JSON 对象，推荐包含：

| 字段 | 语义 |
| --- | --- |
| status | ok / empty / error |
| data | 成功或空结果的工具专属内容；错误时 null |
| sources | 文档 ID/指纹或数据集 ID/版本/指纹，不暴露本机绝对路径 |
| meta | tool_version、可信调用标识、执行时间；统计另含 as_of/window/synthetic |
| warnings | 可解释的局限，例如“历史记录不完整，不能比较增长” |
| error | 成功为 null；失败包含稳定 code 和安全 message |

empty 表示查询合法且来源可用但没有匹配，不是文件缺失或技术失败。统计结果为0时仍为 ok，因为“0”是正常计算结果；无分组记录时可返回 rows=[] 和0总计。

推荐错误代码：INVALID_ARGUMENT、RESOURCE_NOT_FOUND、RESOURCE_AMBIGUOUS、RESOURCE_FORBIDDEN、SOURCE_CHANGED、SOURCE_INVALID、UNSUPPORTED_FIELD、UNSUPPORTED_QUERY、RESULT_TOO_LARGE、INTERNAL_ERROR。不得把错误包装为空结果，不自动放宽查询。

Schema 验证失败在既有调用边界抛出明确参数错误；业务直接调用的薄适配将其映射 INVALID_ARGUMENT。不要修改通用 Runtime 的既有错误协议来强制所有底层输出使用此 envelope。参数通过校验后，三个 handler 的可预期数据访问错误使用上述返回结构。

这是 Tool 结果，不直接冒充 CapabilityResult、Evidence 或 Opportunity。Capability 检查状态并形成领域结果；原文引用及统计口径作为证据来源保存。

## 5. search_knowledge：检索知识资料

### 5.1 输入建议

| 参数 | 约束 |
| --- | --- |
| resource_names | 可选字符串数组；产品正式名、已确认别名或文档 ID；缺省为当前授权资料集合 |
| terms | 必填非空字符串数组，显式检索词，不承诺任意自然语言语义理解 |
| match | all / any，默认 any |
| limit | 正整数，默认5，上限10；属于返回规模限制，不是业务参数 |

Schema 拒绝额外字段、空词和非法类型。首版不引入中文分词库、向量检索或 LLM 查询改写：对规范化文本做显式词项匹配即可。多个 resource_names 取并集，每个名称都须精确命中已登记 ID/别名；一个名称歧义或未知时整体报错，不能静默略过。

### 5.2 检索行为

- Markdown 以真实标题组织章节；目录中的链接和列表不是正文标题，不伪造章节。
- 章节身份用文档ID、文档指纹及该标题行号构成；相同标题出现多次也有不同身份。
- 正文按当前标题至下一个标题前的连续行区间索引；保留完整标题祖先路径。父节和子节分别为检索单元，不隐式合并整份文档。
- 匹配规范化只用于查找，原文输出不改写；保留标题和正文原始行号。
- 排序使用命中词项数量、标题命中等透明规则，再以 doc_id/行号稳定排序；不返回看似有业务意义的概率。
- 返回 top limit 并明确 total_matches、returned_count、truncated。搜索截断不表示资料不存在；用户可缩小词项或文档范围，不为首版实现复杂分页。

### 5.3 输出内容

每个命中含 doc_id、document_title、document_sha256、section_id、heading_path、line_start、line_end、matched_terms、excerpt、excerpt_truncated。excerpt 为短原文片段，不是模型摘要；完整依据必须通过 read_knowledge 读取。节选上限由固定运行配置管理并公开截断标志。

```json
{"resource_names":["御享金越年金"],"terms":["领取方式","领取时间"],"match":"any","limit":5}
```

工具不得把“退休收入需求”自动改成某个产品推荐；检索命中也不证明产品适配。

## 6. read_knowledge：读取原文片段

### 6.1 输入建议

必填 doc_id、document_sha256、line_start、line_end。行号从1开始，区间两端包含；必须位于文档范围内且 start≤end。首版一次最多读取120行，超限返回 RESULT_TOO_LARGE，不静默截断。

doc_id 必须来自当前目录或检索结果，不接受路径。document_sha256 是调用方期望的版本，工具核对实际内容；文件改变返回 SOURCE_CHANGED，要求重新检索，不返回旧行号对应的新文本。

### 6.2 输出内容

返回实际原文 text、文档标题、doc_id、指纹、起止行号及该范围覆盖的标题路径。行号不超范围，不按句子重排，不补写条款。可注明区间可能只是部分章节，不能声称读取片段已经覆盖全部合同限制。

搜索找到保险责任后，Capability 如需判断适用边界，还应读取相关条件/限制；工具不暗中替 Capability 判断哪些条件可以忽略。

产品目录 path 也需检查解析后位于授权根目录，防止配置错误产生越界读；不需要新权限框架。目录中声明的原文版本未知时返回 null，不以文件修改时间冒充官方版本。

## 7. aggregate_records：群体统计

### 7.1 为什么一个统计工具足够

以受控逻辑数据源、字段、筛选、分组和度量复用，不为“统计养老客户”“统计年龄”“统计浏览”分别造工具。首版只支持两个逻辑数据源：customer_profiles 和 customer_behaviors。

这两个 source_id 由装配绑定到当前数据集，不是任意文件路径。数据集中 topics、statement_kind 等枚举可以注入 Tool Schema/description，模型无需猜代码；无需再增加 schema 查询工具。

### 7.2 输入建议

| 参数 | 语义 |
| --- | --- |
| source_id | customer_profiles 或 customer_behaviors |
| time_range | 行为源必填，start/end为带时区ISO时间，左闭右开；档案源禁止填写 |
| filters | 可选数组，每项 field、op、value；数组各条件 AND，单个 in 内部 OR |
| group_by | 可选字段数组，最多2项；空数组表示总计 |
| metrics | 非空度量数组，去重，不允许公式 |

不提供任意排序表达式、join参数、客户ID列表、原文检索过滤、嵌套 OR/NOT 或用户自定义分桶函数。

### 7.3 字段与操作白名单

| 字段 | 来源 | 过滤操作 | 可分组 |
| --- | --- | --- | --- |
| age_years | 两者；行为按 customer_id 关联当前档案年龄 | eq / gte / lte | 否，使用 age_band |
| age_band | 两者；由受控分组配置派生 | eq / in | 是 |
| family_stage | 两者 | eq / in / is_null | 是 |
| topic_code | 行为 | eq / in | 是 |
| event_type | 行为 | eq / in | 是 |
| statement_kind | 行为 | eq / in / is_null | 是 |

is_null 不携带 value，其他操作必须携带匹配字段类型的值；in 为非空数组。不接受用户自定义字段别名。冲突但格式合法的条件可正常得到0；未知字段是错误，不能忽略。

年龄分组来自版本化显示配置，首版使用 Mock 设计的五段；如可用数据超出范围，归入明确的 other，未知归 unknown，不偷偷丢弃。年龄为快照年龄，不宣称是每次行为发生时年龄。

### 7.4 度量白名单和数据集语义

- customer_profiles：只支持 distinct_customers。分析全部档案，不与行为表内连接，无行为客户仍在分母内。
- customer_behaviors：支持 event_count 和 distinct_customers。先按时间筛选，再应用所有过滤条件，最后分组。
- 行为中的年龄/家庭阶段来自固定快照关联，这是唯一内置关联，模型不能选择任意 join。
- 在行为源上，所有行为条件必须由**同一条事件**满足。例如 topic=A AND event_type=consultation，不能用同一客户的A浏览和B咨询拼成A咨询。
- 无行为记录、仅历史记录等差集不作为首版任意查询操作；如需展示，可比较同范围档案总数与明确窗口内活跃独立客户数，并注明推导口径。不要把少量历史数据推导成完整历史覆盖。

```json
{
  "source_id":"customer_behaviors",
  "time_range":{"start":"2026-06-24T00:00:00+08:00","end":"2026-09-22T00:00:00+08:00"},
  "filters":[],
  "group_by":["topic_code"],
  "metrics":["event_count","distinct_customers"]
}
```

另一个查询使用同一工具，filters 中限定 statement_kind=explicit_interest，再按 topic_code 分组，就能统计明确表达人数；无需“识别养老需求人数”专用工具。

### 7.5 结果与分母

data 至少返回：

- rows：分组键和值，以及请求的度量；稳定按分组值排序。
- totals：全匹配集的独立计算总计，不能简单把分组人数求和。
- population_customers：当前数据范围中，应用客户属性过滤后的客户总数；忽略行为过滤和时间窗，表示可比较的人群基础。
- matched_customers：应用全部条件后的独立客户数。
- normalized_query：实际查询条件、窗口与分组配置版本。
- missing：当前筛选前、已应用客户范围和行为时间窗口的数据中，所涉及字段的 null 数量，附 unit=customers/events；明确计数阶段，避免把被过滤的未知值误报为零。

首版不自动生成百分比；如果上层展示占比，必须明确采用 population_customers 还是 matched_customers 作分母。主题人数可重叠，rows之和不一定等于 totals。

分组只返回实际出现的组，空组不补0；null 分组用 JSON null，不能写成“无需求”。没有匹配时返回空 rows 和零 totals；无分组时返回一个总计行，即使是0。

首版最多返回100个分组，超过则 RESULT_TOO_LARGE，要求缩小查询，不截断后声称是全量统计。population_customers 始终是精确计数，不受返回规模影响。

## 8. 资料与统计的通用来源治理

应用装配时只加载允许的文档和验证通过的快照。记录固定的数据/规则指纹；运行中读文件需校验版本，或只消费已加载的不可变快照。不能一次统计用新文件、下一次仍用旧版本标识。

本地数据源无效、客户引用悬空、时间无法解析、重复事件ID等问题是 SOURCE_INVALID，不在查询时静默去掉坏数据。正常事件的客户去重只用于 distinct_customers，与删除重复ID的坏记录不同。

资料中的文字只是被读取的数据，不能改变工具访问范围、追加系统指令或触发外部操作。知识工具不联网、不写文件；统计工具不执行资料中的代码。

结果保留 source_id、版本、查询与调用关联，供 Capability 构造可追溯 Evidence。无需把每条统计结果发布为普通业务产物；现有产物流转仍只发布正式 opportunity。

## 9. Capability 调用示例与停止边界

示例路径，不是硬编码工作流：

1. 检索主推资料中的相关责任、领取及限制章节，按需读取原文。
2. 查询全体客户年龄分布，再查询90天主题行为分布。
3. 对有关注信号的主题查看咨询/明确表达/反向表达，并按需做年龄交叉统计。
4. Capability 比较证据与Goal关系，形成一个机会或说明证据不足。

不要求每次都调满三个工具或固定次数。无匹配、工具错误和证据不足必须可区分；不得为了非空答案修改时间窗、越过数据范围或编造产品关联。普通检索调整可以在该能力内进行，但不生成第二个 Plan。

Tool empty 不直接等于 Capability NO_RESULT：检索未命中也可能是词项不合适。Capability 必须结合支持范围解释，不能无限搜索；具体调用预算在 Capability 实施设计中确定，不建立通用恢复引擎。

## 10. 验收要求

| 场景 | 预期 |
| --- | --- |
| 产品简称与正式名称检索 | 定位相同资料；目录配置变化无需改工具代码 |
| 未知名称或别名歧义 | 明确错误，不静默猜选 |
| 多词匹配、无匹配、重复标题 | all/any准确，empty可区分，引用行号不混淆 |
| 原文读取 | 与源文件指定区间一致，hash一致；不改写内容 |
| 文件改变、越界行号、非法路径参数 | 拒绝，不能读错版本或越权文件 |
| 全部客户年龄分布 | 8/12/14/10/6，合计50，含无行为客户 |
| 90天行为统计 | 105个事件、40位独立客户 |
| 按主题独立客户统计 | 13/10/8/7/6，分组和44，总计40 |
| explicit_interest 过滤 | 分主题8/4/2/1；health无组，总计15，不推断为购买意愿 |
| 增加同人同主题事件 | event_count增加，distinct_customers不增加 |
| 同客户不同主题浏览与咨询 | 同事件AND语义，不交叉拼接出虚假命中 |
| 边界与未知 | 窗口起点计入、终点排除；null不当负例，分母口径明确 |
| 超限/非法字段/数据损坏 | 明确报错，不截断伪装完整结果 |
| 通用性 | 换已登记资料、主题或快照后无需写场景分支；结果随源数据变化 |

年龄、人数基线来自 Mock 数据设计，只有该数据生成并校验后才能执行集成验收；不得直接返回这里列出的数字。为两事件拼接错误增加独立小夹具，不修改正常演示数据配额。

## 11. 后续实施范围建议

推荐先交付三个 Tool 的本地实现、注册工厂、离线测试和最小调用示例。注册工厂只返回 Tool 集合，应用普通映射装配；不修改 Domain、Planner 或 Runtime，不新增包依赖。

产品目录与Mock数据若未生成，先完成对应数据任务；工具单测可用临时小夹具，不伪造正式50人数据已存在。Tool schema需要明确参数类型、默认值、上限和additionalProperties=false；最终校验由既有Tool协议与handler共同完成。

未确认的洞察评分、模型选择、最终Opportunity业务对象及后续圈客协议不纳入这次工具施工。工具实现不意味着 M4 Capability 已完成。

## 12. 给后续开发模型的任务提示词

> 请基于 `doc/design/2026-09-22-insight-tools-design.md` 实现三个通用只读工具 search_knowledge、read_knowledge、aggregate_records。先读 AGENTS.md、当前事实文档、M4与Mock数据设计，核实数据前置条件并保护已有修改。复用 src/agent/tool.py，不新增框架、依赖或第二套工具协议。严格按本文的白名单字段、别名解析、文件版本、同事件筛选语义、分组去重和分母规则实现；工具只读原文或计算统计，不产生机会/推荐/预测NBEV，不开放任意SQL、文件路径或代码。工具结果必须随实际数据变化并保留来源，不能抄预期统计。完成离线验收与源数据变体测试，按实际影响同步 current-state、architecture、dev-log；不顺手实施洞察Agent、Replan、圈客、API或前端，也不声称完整M4已完成。遇到会改变公开协议的设计冲突先指出，不自行新增复杂能力。
