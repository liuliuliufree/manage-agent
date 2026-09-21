
可以。基于你现在的代码状态，我会把项目重新划分成 **M0 已完成 + M1~M8 逐步建设**，并且明确一个原则：

> **`src/model` 和 `src/agent` 到这里基本应该“收住”。下一阶段的主战场不再是继续完善 Agent Loop，而是在它上面建立智慧经营领域层。**

因为你们已经具备了模型抽象、真实/测试模型、Tool 契约、参数校验、Trace、Turn、多轮循环、工具执行、终止控制。按你描述，这已经足够承担一个通用 Agent Runtime。后面的 Goal、Plan、Opportunity、Capability、规则、经营策略都应该作为**上层业务语义**出现，而不是继续塞进 `agent/loop.py`。这也符合当前约束中“底层能力不感知具体业务、一个超级Agent组合 Capability/Tool”的方向。:chatgpt-content-reference{index="0"}

---

# 一、整体 Roadmap

如果按照 **1 周一个 Iteration** 来推进，我建议形成下面这条路线。时间只是节奏参考，真正决定进入下一阶段的是每个 Iteration 的 Exit Criteria。

| Iteration                      | 核心目标                         | 本轮主要开发                                                | 本轮最终必须看到的东西                            | Exit Criteria                                         |
| ------------------------------ | -------------------------------- | ----------------------------------------------------------- | ------------------------------------------------- | ----------------------------------------------------- |
| **M0 已完成**            | 通用 Agent Runtime               | ChatModel、Agent Loop、Tool、Trace/Event、FakeModel         | 一个和业务无关的 Agent 可以多轮调用 Tool          | 现有基础架构稳定，不继续加入经营业务逻辑              |
| **M1 业务契约**          | 建立智慧经营“共同语言”         | Goal、Plan、Capability、Opportunity、Evidence、业务状态语义 | 业务对象能够被结构化表达                          | 不依赖开门红/具体产品也能表达 Goal 和 Capability 调用 |
| **M2 经营超级Agent骨架** | 让自然语言 Goal 真正驱动 Agent   | Goal解析、Plan生成、Capability注册与选择、运行上下文        | 输入一句经营目标，可以看到结构化 Goal + 动态 Plan | Plan不是固定五步；可只选部分 Capability               |
| **M3 重规划机制**        | 从“会调用工具”升级为“会规划” | Capability执行、结果回写、局部 Replan、缺失/失败/阻断状态   | Tool结果能够改变后续 Plan                         | 能跳过、重复、重排 Capability，并处理失败/阻断        |
| **M4 定向洞察 MVP**      | 建立第一条真正业务链路           | 数据/产品知识 Tool、Opportunity 生成、证据组织              | Goal → Opportunity                               | Opportunity 有证据、有来源，不写死开门红结论          |
| **M5 圈客 + 策略 MVP**   | 形成完整只读经营智能             | 动态圈客、客户证据、排序解释、策略生成                      | Goal → Opportunity → 客户 → Strategy           | 能说明为什么选、为什么不选、为什么这样经营            |
| **M6 校验分发**          | 从建议系统进入安全执行系统       | 权限/归属规则 Tool、校验、确认点、任务创建、审计            | 候选客户 → 校验 → 可执行任务                    | 银保客户确定性阻断；写操作有确认、幂等、审计          |
| **M7 追踪迭代闭环**      | 从一次性推荐升级成持续经营       | Feedback/Event、Goal进度、任务结果、Replan                  | 500W → 180W → 剩余320W重新规划                  | 新事实能够驱动重新洞察/圈客/策略                      |
| **M8 通用性与Demo收口**  | 主动验证没有写成开门红工作流     | 跨场景回归、非指定产品、部分能力、重复能力、Goal修改        | 同一套架构跑多个经营问题                          | 不改五类 Capability 主体即可运行新场景                |

这条路线本质上和规范中的验收顺序一致：先证明自然语言 Goal、运行时 Plan、部分 Capability、重复调用和重规划成立，再去验证具体经营能力；最终还必须用非开门红、非指定产品等用例做通用性验证。:chatgpt-content-reference{index="1"} :chatgpt-content-reference{index="2"}

---

# 二、你们现在真正应该做的是 M1，而不是立刻开发“定向洞察”

这是我认为当前最关键的判断。

现在：

```text
ChatModel
    ↓
AgentLoop
    ↓
Tool
```

已经成立。

下一层应该开始出现：

```text
经营超级 Agent
      │
      ├── Goal
      ├── Plan
      ├── Execution Context
      │
      └── Capability
             │
             └── Tool
```

因此最终依赖关系应该逐渐形成：

```text
口袋E / API
      ↓
Business Agent
      ↓
Goal → Plan
      ↓
Capability
      ↓
Agent Loop / Tool Runtime
      ↓
业务 Tool
      ↓
客户数据 / 产品知识 / 模型 / 规则 / 经营平台
```

这里非常重要的一点是：

**Capability ≠ Tool。**

例如：

```text
Capability:
    自动圈客

可能组织：
    customer_query_tool
    customer_feature_tool
    ranking_model_tool
    customer_history_tool
```

Agent 面对的是：

> “为了完成这个 Goal，我现在需要执行自动圈客。”

而 Capability 内部才负责组织完成这件事需要的一个或多个 Tool。

这样以后底层圈客平台换掉，超级 Agent 不需要知道。

---

# 三、M1：业务契约层——我建议下一轮就开发这个

这一轮先**不追求智能**，追求把领域语言稳定下来。

至少应该建立六类概念：

```text
Goal

Plan

CapabilityCall

CapabilityResult

Opportunity

Evidence
```

其中 Goal 可以直接按照现在规范已有定义开始，不需要重新发明：

```text
original_request
goal_type
metric
target
time_horizon
audience_scope
product_or_need_context
channel_and_actor
constraints
success_criteria
missing_information
```

这里最重要的不是字段多少，而是以后所有业务运行都围绕：

```text
goal_id
plan_id
```

建立关联。

而 CapabilityResult 从第一天就建议统一状态，不要让每个能力自己定义：

```text
SUCCESS
PARTIAL_SUCCESS
NEED_INFORMATION
BLOCKED
NO_RESULT
FAILED
```

因为规范已经明确要求不能用一个空列表同时表示“没客户”“数据不足”“规则阻断”“系统错误”。:chatgpt-content-reference{index="3"}

### M1 做完时暂时不要出现什么？

不要出现：

```python
if stage == "开门红":
    ...

if product == "御享分红26":
    ...
```

也不要开始定义：

```text
InsightAgent
CustomerAgent
StrategyAgent
```

你们现在的架构应该继续坚持一个经营超级 Agent。规范也明确禁止因为业务步骤不同机械拆成多个 Agent。:chatgpt-content-reference{index="4"}

---

# 四、M2：第一次真正让“经营超级 Agent”跑起来

这一轮才开始接 LLM。

目标非常简单：

用户输入：

> 当前处于开门红阶段，希望完成500W NBEV，主推御享分红26和御享金越年金。

系统先产生：

```text
Natural Language
        ↓
Structured Goal
```

然后再让超级 Agent 判断：

```text
当前为了完成这个 Goal，
需要调用哪些 Capability？
```

得到类似：

```text
Plan

Step 1
Capability: directional_insight
Reason:
需要先识别目标的潜在经营来源

Step 2
Capability: customer_targeting
Depends on:
Step 1 Opportunity

Step 3
Capability: strategy_generation

Step 4
Capability: validation
```

但重点不是这个结果。

重点是它**还必须允许生成另外一种 Plan**。

比如用户说：

> 王女士下一步应该怎么经营？

可能直接得到：

```text
strategy_generation
        ↓
validation
```

而不是：

```text
洞察
↓
圈客
↓
策略
↓
校验
↓
追踪
```

否则项目会在这个阶段直接退化成五节点 Workflow。

规范对此已经非常明确：Plan 必须运行时生成，五类 Capability 可以跳过、重复、重排。:chatgpt-content-reference{index="5"}

---

# 五、M3 是一个很容易被低估，但极其重要的阶段：Replan

我甚至建议在真正开发洞察之前，先把 Replan 做出来。

比如你需要 FakeCapability 模拟下面几种情况：

```text
Case A
Insight → SUCCESS

Case B
Insight → NO_RESULT

Case C
CustomerTargeting → NEED_INFORMATION

Case D
Validation → BLOCKED

Case E
Strategy → FAILED
```

然后验证超级 Agent 会不会决定：

```text
继续
跳过
重新调用
换一个 Capability
询问用户
停止
```

例如：

```text
Plan
 ├─ insight
 ├─ targeting
 └─ strategy
```

执行 targeting 后：

```text
NO_RESULT
```

这时候不能简单：

```text
return error
```

而应该进入：

```text
Agent Loop
    ↓
读取 Capability Result
    ↓
Replan
    ↓
调整 Opportunity / 条件
    ↓
再次 targeting
```

到这里，你的 `AgentLoop` 才真正从一个：

> Tool Calling Loop

变成：

> Business Planning Runtime。

---

# 六、M4 才开始真正开发“定向洞察”

这时候先做一个**非常窄的 Capability**。

比如：

```text
Goal
    ↓
Directional Insight
    ↓
Opportunity[]
```

第一版甚至只需要支持：

```text
2~3 个 Opportunity
```

数据可以 Mock。

产品知识也可以 Mock。

模型可以非常简单。

因为规范明确允许 Demo 简化数据量、模型复杂度、Opportunity 数量和部分 Tool 实现；真正不能简化的是动态规划、权限校验、事实来源和业务边界。:chatgpt-content-reference{index="6"}

但 Opportunity 从第一版开始就应该认真：

```text
opportunity_id

goal_link

problem_statement

evidence

eligibility

exclusions

priority

validity

candidate_logic

next_actions
```

这样未来：

```text
养老现金流机会
```

才能真正成为：

```text
Opportunity
        ↓
candidate_logic
        ↓
自动圈客
```

而不是：

```python
if opportunity == "养老":
    age > 45
    and income > ...
```

写死在代码里。

---

# 七、M5：第一次形成完整“只读经营智能”

这一阶段把三个能力串起来：

```text
Goal

  ↓

Opportunity

  ↓

Candidate Customers

  ↓

Strategy
```

到这一版本，其实已经可以做一次非常漂亮的内部 Demo。

因为代理人已经可以看到：

```text
我要完成什么
↓
有哪些经营机会
↓
为什么是这些客户
↓
为什么是这个客户
↓
应该怎么经营
```

但这个版本**仍然不创建真实经营任务**。

这一点要刻意控制。

因为：

```text
Candidate Customer
```

绝对不能直接等于：

```text
Executable Customer
```

规范把这两个状态分得非常清楚。:chatgpt-content-reference{index="7"}

---

# 八、M6 是第二个架构分水岭：校验分发

从这里开始加入：

```text
channel_rule_tool

customer_ownership_tool

actor_permission_tool

business_restriction_tool

task_creation_tool
```

Agent 可以：

```text
解释结果
```

但不能：

```text
决定规则结果。
```

例如：

```text
Customer D

经营价值：High
产品适配：High

↓ validation

客户渠道：银保
当前渠道：个险

↓ deterministic rule

BLOCKED
```

Agent 只能说：

> 客户具有经营价值，但当前不属于当前代理人的合法经营范围。

不能：

> 因为价值特别高，所以这次放行。

这正是这个项目里最重要的 Agent / Deterministic Rule 边界之一。:chatgpt-content-reference{index="8"}

---

# 九、M7：实现真正意义上的闭环

这时候项目的状态模型开始出现：

```text
Goal
 │
 ├─ Plan V1
 │    ├─ Opportunity
 │    ├─ Customer
 │    ├─ Strategy
 │    └─ Task
 │
 ├─ Feedback Events
 │
 └─ Plan V2
```

例如：

```text
Goal = 500W

第一轮完成
180W

Feedback:
养老型客户响应明显更好

↓

Remaining Goal = 320W

↓

Replan

↓

提高养老 Opportunity priority

↓

重新圈客

↓

新的 Strategy
```

这时候业务故事里的“追踪迭代”才不是一个单独功能页面，而成为**整个 Agent Runtime 的输入来源**。

这一步跑通以后，我才会认为：

> “智慧经营超级 Agent 的核心架构完成了。”

---

# 十、M8 不应该继续加功能，而应该开始“攻击自己的架构”

最后一轮不要继续做漂亮 Demo。

要专门写一些难看的测试。

比如：

```text
Case 1
非开门红

Case 2
产品完全换掉

Case 3
只要求洞察

Case 4
指定一个客户，不需要圈客

Case 5
同一 Capability 调两次

Case 6
规则阻断

Case 7
用户运行中修改 Goal
```

如果此时需要：

```python
if special_scene:
```

或者：

```text
新增一套 Prompt
新增一套 Workflow
复制一个 CustomerTargeting
```

就说明前面的抽象存在问题。

规范甚至已经把这些情况明确列为必须覆盖的通用性测试。:chatgpt-content-reference{index="9"}

---

# 十一、这样看，你们现在的位置其实非常清楚

现在是：

```text
                    当前
                     ↓
LLM abstraction ─ Agent Loop
                     │
                     │
              ───────┴───────
              下一阶段开始
                     │
                    Goal
                     ↓
                    Plan
                     ↓
                Capability
                     ↓
                    Tool
                     ↓
          Data / Model / Rule / Knowledge
```

所以我建议你们**下一轮不要碰洞察算法、不要碰复杂圈客、也不要急着做页面**。

下一轮就集中解决三个问题：

> **① Goal 在系统中到底长什么样？**
> **② Plan 在系统中到底长什么样？**
> **③ Capability 如何建立在当前 Tool + AgentLoop 之上？**

把这三个问题解决，项目后面基本就是沿着正确轨道“长肉”。

反过来，如果现在直接开始写“开门红洞察 Tool”“养老客户圈客 Tool”“御享分红策略 Tool”，很快就会得到一个能够演示、但很难演化的系统。

另外建议从下一轮开始，每一个 Iteration 都坚持同一个 Definition of Done：

**代码跑通 → FakeModel/FakeTool 测试 → 异常路径测试 → 更新 `current-state.md` → 如架构变化更新 `architecture.md` → 在 `dev-log.md` 记录验证结果。** 这也符合当前项目对事实源、验证基线和开发后文档同步的要求。:chatgpt-content-reference{index="10"}

**因此，如果我们马上进入实际开发，我建议下一步直接把 M1 拆成具体任务：先设计 `Goal / Plan / Capability / Opportunity / Evidence` 这五个核心契约，以及它们和你现有 `AgentLoop / Tool / Trace` 的关系。** 这会是 Roadmap 上第一个真正需要做设计决策的地方。
