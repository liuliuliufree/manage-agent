# 前三幕 Demo 合成源数据说明

## 1. 数据集用途

本目录保存领导 Demo 前三幕使用的合成原始数据：

1. 经营人员提出目标与边界；
2. 主 Agent 调用工具分析多个候选机会；
3. 主 Agent 调用工具完成自动圈客并解释结果。

这些 CSV 模拟未来可能来自客户、保单、授权、行为、触达、投诉理赔和规则系统的数据。数据不包含真实客户信息，不代表真实业务分布，也不能用于生产决策。

本目录只保存业务运行可以读取的原始事实和规则配置，不保存以下最终结论：

- 最终推荐哪个机会；
- 86→41→12 漏斗；
- 客户是否可经营；
- 客户排除原因；
- 客户优先级及最终解释。

这些结论必须由代码根据本目录中的数据重新计算。测试期望单独保存在相邻的 `test_expectations` 目录，业务 Tool 和主 Agent 不得读取测试期望。

## 2. 场景摘要

| 项目                   | 当前值                        |
| ---------------------- | ----------------------------- |
| 场景标识               | `demo-acts-1-3`             |
| 场景版本               | `1.0.0`                     |
| 数据模式               | `synthetic`                 |
| 数据基准时间           | `2026-09-15T09:00:00+08:00` |
| 客户总数               | 120                           |
| 第一类机会规模         | 86                            |
| 第二类机会规模         | 50                            |
| 第三类机会规模         | 25                            |
| 第一类机会可经营人数   | 41                            |
| 第一类机会高优先级人数 | 12                            |

三个机会允许存在客户重叠，因此三个机会规模之和不等于客户总数。

## 3. 文件清单

| 文件                               | 数据行数 | 主要用途                           |
| ---------------------------------- | -------: | ---------------------------------- |
| `scenario.csv`                   |        1 | 场景版本、基准时间和规则版本       |
| `business_request.csv`           |        1 | 第一幕的经营目标和用户边界         |
| `customer_profile.csv`           |      120 | 客户基础画像                       |
| `family_responsibility_fact.csv` |      120 | 家庭责任和所需保障额度             |
| `policy_coverage.csv`            |      120 | 已有重疾保障和保单周年日           |
| `authorization.csv`              |      240 | 数据使用授权与经营接触授权         |
| `behavior_event.csv`             |      112 | 浏览、测算、咨询和家庭信息更新事件 |
| `contact_event.csv`              |       41 | 历史经营触达和明确拒绝事件         |
| `sensitive_status.csv`           |        6 | 投诉、理赔等敏感状态               |
| `suitability_fact.csv`           |      120 | 初步适当性所需事实                 |
| `opportunity_definition.csv`     |        3 | 三个候选机会的业务定义             |
| `calculation_rule.csv`           |       17 | 机会、初筛和优先级计算参数         |

CSV 使用 UTF-8 with BOM 编码，便于在 Windows 和 Excel 中直接查看。时间戳使用 ISO 8601 格式并带 `+08:00` 时区。

## 4. 数据关系

```text
scenario
├─ business_request
├─ opportunity_definition
├─ calculation_rule
└─ customer_profile
   ├─ family_responsibility_fact ── authorization(data_use)
   ├─ policy_coverage
   ├─ authorization(business_contact)
   ├─ behavior_event
   ├─ contact_event
   ├─ sensitive_status
   └─ suitability_fact
```

主要关联关系：

- 所有文件通过 `scenario_id` 归属于同一个场景。
- 客户相关文件通过 `customer_id` 关联 `customer_profile.csv`。
- `family_responsibility_fact.authorization_id` 必须关联一条 `scope=data_use` 的授权记录。
- 一个客户可以拥有多条授权、行为和触达记录。
- 当前每位客户恰好有一条家庭责任事实、一条重疾保障记录和一条初步适当性事实；这是首版场景简化，不是生产约束。

## 5. 通用约定

### 5.1 标识

- 客户标识采用 `C001` 至 `C120`。
- 各表业务标识带有可读前缀，例如 `POL-`、`AUTH-`、`BEH-`。
- 所有标识均为合成标识，不映射真实客户或真实业务记录。

### 5.2 空值

CSV 中的空字符串表示该字段在当前记录上不适用。例如数据使用授权没有撤回时间时，`withdrawn_at` 为空。

### 5.3 布尔值

布尔字段统一使用小写字符串：

- `true`
- `false`

### 5.4 金额

保障额度和保费均使用整数，不带千位分隔符。当前场景按人民币语义理解，但 CSV 不承担币种换算。

### 5.5 时间

所有“近期”“近 30 天”“7 天频控”等相对时间，都以 `scenario.csv` 中的 `baseline_at` 为基准计算，不能使用程序实际运行时间。

## 6. 各表字段说明

### 6.1 `scenario.csv`

一行代表一套可重复运行的演示场景。

| 字段                        | 含义                              |
| --------------------------- | --------------------------------- |
| `scenario_id`             | 场景唯一标识                      |
| `scenario_version`        | 场景内容版本                      |
| `baseline_at`             | 相对时间统一基准                  |
| `random_seed`             | 批量生成和并列排序的固定种子      |
| `data_mode`               | 数据模式，当前固定为`synthetic` |
| `data_definition_version` | 数据字段和口径版本                |
| `rule_version`            | 当前规则版本                      |
| `description`             | 场景的人类可读说明                |

### 6.2 `business_request.csv`

保存第一幕中经营人员实际输入的信息，不包含 Agent 整理后的结构化任务。

| 字段                | 含义                         |
| ------------------- | ---------------------------- |
| `request_id`      | 请求标识                     |
| `scenario_id`     | 所属场景                     |
| `goal_text`       | 经营人员的原始自然语言目标   |
| `analysis_window` | 用户指定的分析范围           |
| `desired_outcome` | 希望得到的经营结果           |
| `boundaries`      | 三条用户边界组成的 JSON 数组 |
| `requested_at`    | 请求时间                     |
| `requester_role`  | 请求主体角色                 |

`boundaries` 虽然位于 CSV 单元格中，但内容是 JSON 数组。每条边界包含原文、来源和是否属于硬边界。主 Agent 可以整理其表达，但不能放宽硬边界。

### 6.3 `customer_profile.csv`

保存前三幕实际消费的最小客户画像。

| 字段                      | 含义             |
| ------------------------- | ---------------- |
| `scenario_id`           | 所属场景         |
| `customer_id`           | 合成客户标识     |
| `age`                   | 演示使用的年龄   |
| `family_stage`          | 家庭阶段         |
| `dependent_count`       | 被抚养人数       |
| `income_band`           | 年收入区间       |
| `payment_capacity_band` | 持续缴费能力区间 |
| `profile_updated_at`    | 画像更新时间     |

`income_band` 和 `payment_capacity_band` 是合成区间，不是精确收入或正式财务评估。

`family_stage` 当前使用：

- `raising_children`：育儿阶段；
- `supporting_family`：承担较高家庭责任；
- `single`：单身或低家庭责任；
- `empty_nest`：低被抚养责任阶段。

### 6.4 `family_responsibility_fact.csv`

保存家庭责任和保障需求测算的原始输入。

| 字段                         | 含义                         |
| ---------------------------- | ---------------------------- |
| `fact_id`                  | 家庭责任事实标识             |
| `scenario_id`              | 所属场景                     |
| `customer_id`              | 客户标识                     |
| `responsibility_level`     | 家庭责任级别                 |
| `required_coverage_amount` | 按场景口径测算的所需保障额度 |
| `source_type`              | 信息来源                     |
| `occurred_at`              | 信息产生或更新时间           |
| `valid_until`              | 事实有效期                   |
| `authorization_id`         | 允许使用该事实的授权记录     |

当前 `source_type` 使用：

- `customer_update`：客户主动更新；
- `protection_assessment`：客户参与保障测算后产生。

该表不保存“保障缺口”字段。保障缺口必须使用：

```text
所需保障额度 - 当前有效重疾保障额度
```

重新计算。

### 6.5 `policy_coverage.csv`

当前每位客户有一条有效重疾保障记录。

| 字段                      | 含义                                 |
| ------------------------- | ------------------------------------ |
| `policy_id`             | 合成保单标识                         |
| `scenario_id`           | 所属场景                             |
| `customer_id`           | 客户标识                             |
| `coverage_type`         | 保障类别，当前为`critical_illness` |
| `insured_amount`        | 当前有效保障额度                     |
| `annual_premium`        | 年缴保费                             |
| `payment_period`        | 缴费周期                             |
| `effective_at`          | 保单生效时间                         |
| `next_anniversary_date` | 下一保单周年日                       |
| `status`                | 保单状态，当前为`active`           |

第二类机会通过 `next_anniversary_date` 与场景基准日期的距离计算。

### 6.6 `authorization.csv`

每位客户有两条不同语义的授权：

1. `scope=data_use`：是否允许使用家庭责任信息进行保障分析；
2. `scope=business_contact`：是否允许围绕保障检视开展经营接触。

两者必须分别判断。允许系统分析客户已授权的数据，不代表允许向该客户开展经营接触。

| 字段                 | 含义                                     |
| -------------------- | ---------------------------------------- |
| `authorization_id` | 授权标识                                 |
| `scenario_id`      | 所属场景                                 |
| `customer_id`      | 客户标识                                 |
| `scope`            | `data_use` 或 `business_contact`     |
| `data_category`    | 被授权使用的数据类别；经营接触记录可为空 |
| `purpose`          | 授权用途                                 |
| `status`           | `active` 或 `withdrawn`              |
| `effective_at`     | 生效时间                                 |
| `expires_at`       | 失效时间                                 |
| `source`           | 授权来源                                 |
| `withdrawn_at`     | 撤回时间，未撤回时为空                   |

当前不包含短信、电话、App 等具体渠道许可；该部分属于后续策略与执行环节。

### 6.7 `behavior_event.csv`

保存客户主动行为，事件本身不携带“高意向”结论。

| 字段            | 含义                                 |
| --------------- | ------------------------------------ |
| `event_id`    | 行为事件标识                         |
| `scenario_id` | 所属场景                             |
| `customer_id` | 客户标识                             |
| `event_type`  | 行为类型                             |
| `subject`     | 行为对象，例如重疾或医疗保障         |
| `occurred_at` | 行为发生时间                         |
| `source`      | 事件来源                             |
| `metadata`    | 预留的少量事件补充信息，当前为`{}` |

当前 `event_type` 包括：

- `family_information_updated`；
- `content_viewed`；
- `assessment_started`；
- `assessment_completed`；
- `consultation_started`。

当前 `subject` 包括：

- `family_responsibility`；
- `critical_illness`；
- `medical`。

### 6.8 `contact_event.csv`

保存已经发生的经营触达，用于频控和明确拒绝判断。

| 字段             | 含义                        |
| ---------------- | --------------------------- |
| `event_id`     | 触达事件标识                |
| `scenario_id`  | 所属场景                    |
| `customer_id`  | 客户标识                    |
| `contact_type` | 当前为`marketing`         |
| `purpose`      | 当前为`protection_review` |
| `occurred_at`  | 触达发生时间                |
| `result`       | 触达结果                    |
| `source`       | 事件来源                    |

当前 `result` 包括：

- `opened`；
- `no_response`；
- `explicit_refusal`。

频控次数从该表事件明细计算，不存在独立维护的“最近 7 天触达次数”字段。

### 6.9 `sensitive_status.csv`

只记录当前会暂停经营的敏感状态，不保存投诉或理赔详情。

| 字段                | 含义                                               |
| ------------------- | -------------------------------------------------- |
| `status_id`       | 敏感状态标识                                       |
| `scenario_id`     | 所属场景                                           |
| `customer_id`     | 客户标识                                           |
| `status_type`     | `claim_in_progress` 或 `complaint_in_progress` |
| `started_at`      | 状态开始时间                                       |
| `expected_end_at` | 预计结束或复核时间                                 |
| `status`          | 当前为`active`                                   |
| `source`          | 状态来源                                           |

未出现在该表中的客户表示当前没有已知的敏感阻断状态。

### 6.10 `suitability_fact.csv`

保存初步适当性判断需要的事实，不直接保存最终是否通过。

| 字段                             | 含义                           |
| -------------------------------- | ------------------------------ |
| `fact_id`                      | 事实标识                       |
| `scenario_id`                  | 所属场景                       |
| `customer_id`                  | 客户标识                       |
| `information_complete`         | 初步信息是否完整               |
| `payment_capacity_available`   | 是否存在缴费能力依据           |
| `candidate_scope_available`    | 是否存在可进一步评估的产品范围 |
| `professional_review_required` | 是否必须由专业人员继续确认     |
| `evaluated_at`                 | 事实更新时间                   |
| `definition_version`           | 适当性事实口径版本             |

当前所有客户的 `professional_review_required` 都为 `true`，表示第三幕最多允许进入保障检视，不能直接形成具体产品销售建议。该字段为 `true` 不代表初筛失败。

### 6.11 `opportunity_definition.csv`

三行分别定义三个候选机会：

| `opportunity_id`         | 机会                         |
| -------------------------- | ---------------------------- |
| `OPP-FAMILY-CI-GAP`      | 家庭责任变化与重疾保障缺口   |
| `OPP-POLICY-ANNIVERSARY` | 临近保单周年的保障回顾       |
| `OPP-MEDICAL-INCOMPLETE` | 主动了解医疗保障但未完成测算 |

字段说明：

| 字段                     | 含义                   |
| ------------------------ | ---------------------- |
| `opportunity_id`       | 机会标识               |
| `scenario_id`          | 所属场景               |
| `name`                 | 机会名称               |
| `description`          | 业务定义               |
| `required_signals`     | 必须满足的信号，以 `   |
| `optional_signals`     | 增强机会或评分的信号   |
| `exclusion_conditions` | 机会识别阶段的排除条件 |
| `definition_version`   | 机会定义版本           |

该表描述业务口径，不保存每位客户是否命中机会。

### 6.12 `calculation_rule.csv`

保存当前生成器和后续确定性 Tool 使用的透明参数。

| 字段                | 含义                                             |
| ------------------- | ------------------------------------------------ |
| `rule_id`         | 规则标识                                         |
| `scenario_id`     | 所属场景                                         |
| `rule_group`      | `OPPORTUNITY`、`ELIGIBILITY` 或 `PRIORITY` |
| `parameter_name`  | 参数名称                                         |
| `parameter_value` | 参数值                                           |
| `value_type`      | `integer` 或 `decimal`                       |
| `effective_at`    | 生效时间                                         |
| `version`         | 规则版本                                         |
| `description`     | 参数的业务含义                                   |

主要规则包括：

- 家庭责任事实有效 180 天；
- 保单周年机会窗口 30 天；
- 主动行为有效窗口 30 天；
- 频控窗口 7 天；
- 频控窗口内营销触达达到 3 次即暂缓；
- 高优先级客户取前 12 名；
- 优先级由保障缺口、家庭事实新鲜度、浏览、测算、咨询、缴费能力和近期触达扣减共同计算。

## 7. 三个机会如何从源数据产生

### 7.1 家庭责任变化与重疾保障缺口

客户需要同时满足：

- 家庭责任为中或高；
- 家庭责任事实在有效期内；
- 家庭责任信息的数据使用授权有效；
- 所需保障额度大于当前有效重疾保障额度。

当前数据计算得到 86 名客户，即 C001 至 C086。

### 7.2 临近保单周年的保障回顾

客户需要存在有效保单，且下一周年日在基准日期之后 30 天以内。

当前数据计算得到 50 名客户，即 C030 至 C079。

### 7.3 主动了解医疗保障但未完成测算

客户需要在近 30 天内：

- 浏览医疗保障内容；
- 开始医疗保障测算；
- 尚未完成医疗保障测算。

当前数据计算得到 25 名客户，即 C081 至 C105。

第二、第三类机会的具体人数不是长期业务契约，但当前生成结果应保持可重复。

## 8. 第一类机会如何形成 86→41→12

### 8.1 经营初筛

86 名机会客户需要依次通过：

1. 经营接触授权有效；
2. 没有明确拒绝或退订；
3. 没有生效中的投诉、理赔等敏感状态；
4. 近 7 天营销触达少于 3 次；
5. 初步信息、缴费能力依据和候选产品范围均可用。

当前有 41 名客户通过。45 名排除客户按主要原因分布为：

| 客户范围   | 主要原因             | 人数 |
| ---------- | -------------------- | ---: |
| C042–C055 | 经营接触授权已撤回   |   14 |
| C056–C064 | 近 7 天触达达到 3 次 |    9 |
| C065–C071 | 已明确拒绝           |    7 |
| C072–C077 | 投诉或理赔处理中     |    6 |
| C078–C086 | 初步适当性事实不足   |    9 |

如果未来某位客户同时命中多个排除原因，系统仍应保存全部命中记录，并按固定优先级选择一个主要展示原因。

### 8.2 高优先级排序

硬规则只决定是否可经营。优先级只在 41 名可经营客户中计算，高分不能覆盖硬规则失败。

当前优先级计算为：

```text
保障缺口贡献
+ 30 天内家庭责任事实贡献
+ 近期重疾内容浏览贡献（最多两次）
+ 完成重疾保障测算贡献
+ 主动咨询贡献
+ 缴费能力区间贡献
- 近 7 天营销触达扣减
```

按得分降序、客户标识升序处理并列后，取前 12 名：

```text
C001, C002, C003, C004, C005, C006,
C007, C008, C009, C010, C011, C028
```

第三幕的圈客优先级分不同于第六幕的实时意向分，两者不能混用。

## 9. 关键客户核验

### 9.1 C001

C001 是主要正向角色：

- 35 岁；
- 家庭责任信息由客户主动更新且数据使用授权有效；
- 所需保障额度为 120 万，当前重疾保障低于所需额度；
- 近 30 天两次查看重疾保障内容；
- 完成一次重疾保障测算；
- 经营接触授权有效；
- 近 7 天没有营销触达；
- 没有明确拒绝或敏感状态；
- 初步适当性事实完整；
- 当前优先级得分为 105，进入高优先级。

### 9.2 C028

C028 用于后续演示“高潜力不等于始终允许触达”：

- 第三幕初始快照中通过全部硬规则；
- 近 7 天已有 2 次营销触达，尚未达到 3 次频控阈值；
- 主动行为和保障缺口使其当前得分为 100；
- 第三幕仍进入高优先级。

第三幕后将由后续场景注入一条新的外部触达事件。届时 C028 达到频控阈值，在第五幕执行前复检时被暂缓。该未来事件不在本目录中，避免提前污染前三幕快照。

## 10. 数据生成与校验

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_mock_data.py
```

该命令会重新生成本目录中的全部 CSV，并立即从 CSV 原始事实重算关键结果。

只校验已有数据：

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_mock_data.py --validate-only
```

运行自动化测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

正常校验摘要应包含：

```text
客户总数：120
三个机会规模：86、50、25
可经营客户：41
高优先级客户：12
排除分布：14、9、7、6、9
C001 得分：105
C028 得分：100
```

生成器只覆盖这套场景明确拥有的 12 份源 CSV 和 1 份测试期望 CSV，不会删除输出目录中的其他文件。

## 11. 人工修改注意事项

- 不要直接修改漏斗或优先级期望来掩盖源数据问题。
- 修改客户事实后必须重新运行 `--validate-only`。
- 修改基准时间时，需要同步检查全部事件、授权和有效期。
- 修改频控规则时，需要重新核对 C028 的第三幕状态。
- 修改评分参数时，需要确认高优先级仍然是 12 人，并核对 C001、C028。
- 新增字段前先确认前三幕是否实际消费该字段，避免提前复制生产数据模型。
- 所有新增数据都必须保持合成性质，不得混入真实客户数据。
