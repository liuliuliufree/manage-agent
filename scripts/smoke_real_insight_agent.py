"""真实发送一次第一幕到第二幕业务场景，并输出可审计动作叙事。

reason 是应用公开的决策依据，不是模型隐藏思维链。
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, sys, threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.application.business_agent import BusinessAgent, BusinessAgentStatus
from src.application.capability.artifact_flow import CapabilityIO
from src.application.capability.artifact_store import ArtifactStore
from src.application.capability.capability_executor import CapabilityExecutor
from src.application.customer_selection import CUSTOMER_TARGETING_IO, CustomerSelectionConfig, make_customer_targeting_handler
from src.application.goal_parser import GoalParser, RuntimeContext
from src.application.insight_tools import InsightToolConfig, build_insight_tools
from src.application.planner.planner import Planner
from src.domain import CapabilityError, CapabilityOutput, CapabilityResult, CapabilityStatus, ErrorCategory
from src.model import ChatModelSettings, OpenAIChatModel

REQUEST = "当前处于开门红阶段，希望完成500W NBEV，主推御享分红26和御享金越年金。"
ACTOR, CHANNEL = "AGENT_DEMO_001", "individual"
AS_OF = "2026-09-22T00:00:00+08:00"
WINDOW = {"start":"2026-06-24T00:00:00+08:00", "end":AS_OF}

class Narrative:
    def __init__(self): self.seq = 0
    def emit(self, act, action, reason, result, basis="program_rule", status="completed"):
        self.seq += 1
        print(json.dumps({"sequence":self.seq,"act":act,"action":action,"reason":reason,"basis":basis,"status":status,"result":result}, ensure_ascii=False, default=str), flush=True)

def sync(value):
    if not hasattr(value, "__await__"): return value
    box = {}
    def run():
        try: box["value"] = asyncio.run(value)
        except BaseException as exc: box["error"] = exc
    thread = threading.Thread(target=run); thread.start(); thread.join()
    if "error" in box: raise box["error"]
    return box["value"]

def model_json(completion):
    value = json.loads(completion.choices[0].message.content)
    if not isinstance(value, dict): raise ValueError("model response must be an object")
    return value

def make_directional_handler(model, model_name, store, log):
    tools = {tool.name:tool for tool in build_insight_tools(InsightToolConfig.from_repository(ROOT))}
    def call(name, args, reason):
        result = sync(tools[name].handler(args))
        log.emit("第一幕", f"调用工具 {name}", reason, {"arguments":args,"response":result}, "source_fact")
        if result.get("status") != "ok": raise RuntimeError(f"{name}: {result.get('error')}")
        return result
    def handler(request):
        def failed(code, message):
            return CapabilityResult(request.request_id, request.capability_id, CapabilityStatus.FAILED, errors=(CapabilityError(ErrorCategory.VALIDATION, code, message),))
        try:
            if (request.actor_context.actor_id, request.actor_context.channel_id) != (ACTOR, CHANNEL):
                return failed("INSIGHT_SCOPE_FORBIDDEN", "actor/channel is outside the bound snapshot")
            search = call("search_knowledge", {"terms":["领取","分红"],"match":"any","limit":10}, "经营方向必须受主推产品原始资料的领取条件和分红不确定性约束。")
            excerpts = [call("read_knowledge", {"doc_id":m["doc_id"],"document_sha256":m["document_sha256"],"line_start":m["line_start"],"line_end":m["line_end"]}, "检索只给定位，必须按指纹和行号读取原文后才能引用。") for m in search["data"]["matches"]]
            aggregate = call("aggregate_records", {"source_id":"customer_behaviors","time_range":WINDOW,"group_by":["topic_code"],"metrics":["event_count","distinct_customers"]}, "比较授权快照各主题的真实关注规模，不能从目标金额倒推机会。")
            interest = call("aggregate_records", {"source_id":"customer_behaviors","time_range":WINDOW,"filters":[{"field":"statement_kind","op":"eq","value":"explicit_interest"}],"group_by":["topic_code"],"metrics":["event_count","distinct_customers"]}, "补充进一步了解信号；该字段不能当成明确自身需求。")
            topics_doc = json.loads((ROOT/"data/client/topics.json").read_text(encoding="utf-8"))
            payload = {"goal_ref":{"goal_id":request.goal_ref.goal_id,"version":request.goal_ref.version},"registered_topics":topics_doc["topics"],"knowledge_excerpts":excerpts,"behavior_by_topic":aggregate,"explicit_interest_by_topic":interest,"output":{"topic_code":"registered","opportunity_type":"string","problem_statement":"question worth verifying","priority_reason":"string","limitations":["string"]}}
            inferred = model_json(sync(model.complete({"model":model_name,"temperature":0,"response_format":{"type":"json_object"},"messages":[{"role":"system","content":"从可信资料和聚合事实形成一个优先经营机会，只输出JSON。不得生成客户名单、产品适配、成交概率或NBEV预测；explicit_interest不等于明确需求。必须使用已登记topic_code并保留限制。"},{"role":"user","content":json.dumps(payload,ensure_ascii=False)}]})))
            required = {"topic_code","opportunity_type","problem_statement","priority_reason","limitations"}
            allowed = {item["topic_code"] for item in topics_doc["topics"]}
            if set(inferred) != required or inferred["topic_code"] not in allowed or not isinstance(inferred["limitations"],list): raise ValueError("directional insight output invalid")
            manifest = json.loads((ROOT/"data/client/manifest.json").read_text(encoding="utf-8"))
            oid = f"opportunity_{request.request_id}"
            opportunity = {"opportunity_id":oid,"goal_ref":{"goal_id":request.goal_ref.goal_id,"version":request.goal_ref.version},"opportunity_type":inferred["opportunity_type"],"problem_statement":inferred["problem_statement"],"priority":"high","priority_reason":inferred["priority_reason"],"evidence_scope":{"topic_codes":[inferred["topic_code"]]},"limitations":inferred["limitations"],"inference_type":"model_inference","data_source":{"dataset_id":manifest["dataset_id"],"version":manifest["version"],"manifest_sha256":hashlib.sha256((ROOT/"data/client/manifest.json").read_bytes()).hexdigest().upper()},"audit":{"model":model_name,"prompt_version":"directional-opportunity-v1","observed_at":AS_OF}}
            store.put("opportunity", oid, opportunity)
            log.emit("第一幕","形成并校验优先经营机会","模型负责语义提炼；程序负责主题白名单、结构、Goal与数据版本绑定。",opportunity,"model_inference+program_rule")
            return CapabilityResult(request.request_id,request.capability_id,CapabilityStatus.SUCCESS,outputs=(CapabilityOutput(oid,"opportunity","One evidence-bounded priority opportunity."),),limitations=("Model inference is not deterministic proof.",))
        except Exception as exc: return failed("DIRECTIONAL_INSIGHT_FAILED",str(exc))
    return handler

def _has_positive_business_claim(text: str) -> bool:
    """Reject positive product/forecast claims while allowing limitation wording."""
    import re
    patterns = (
        r"(?:预计(?:将|可以|能|可)?(?:贡献)?|预测(?:将|可以|能|可)?(?:贡献)?|可贡献|能够贡献|贡献约)\s*[\d,.]+\s*(?:万|亿|元|W)?\s*NBEV",
        r"(?:适合|推荐)\s*(?:购买|投保|配置)",
        r"(?:保证|确定)\s*(?:收益|分红)",
        r"已完成\s*500\s*[万W]",
    )
    negative = ("不能", "不应", "不建议", "不表示", "不等于", "尚不能", "避免")
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = text[max(0, match.start()-10):match.start()]
            if not any(marker in prefix for marker in negative): return True
    return False
def concise(entry: Mapping[str,Any]):
    return {key:entry.get(key) for key in ("customer_id","display_name","need_state","need_summary","reason","information_to_verify","evidence")}

async def run(user_request):
    log, store = Narrative(), ArtifactStore()
    settings = ChatModelSettings.from_env(ROOT/".env"); model = OpenAIChatModel(settings); insight_model = OpenAIChatModel(settings); selection_model = OpenAIChatModel(settings)
    try:
        log.emit("入口","接收经营目标","自然语言目标是本次独立运行的唯一业务入口。",user_request,"user_input")
        insight = InsightToolConfig.from_repository(ROOT)
        selection_config = CustomerSelectionConfig(insight=insight,actor_id=ACTOR,channel_id=CHANNEL)
        handlers = {"directional_insight":make_directional_handler(insight_model,settings.model,store,log),"customer_targeting":make_customer_targeting_handler(selection_config,model=selection_model,artifact_store=store)}
        agent = BusinessAgent(goal_parser=GoalParser(model=model,model_name=settings.model,goal_id_factory=lambda:"goal_opening_campaign"),planner=Planner(model=model,model_name=settings.model,plan_id_factory=lambda:"plan_opening_campaign_v1"),capability_executor=CapabilityExecutor(handlers),capability_io={"directional_insight":CapabilityIO(output_types=("opportunity",)),"customer_targeting":CUSTOMER_TARGETING_IO},capability_catalog={"directional_insight":{"description":"识别与当前经营目标相关的经营机会"},"customer_targeting":{"description":"围绕明确经营机会寻找候选客户"}})
        log.emit("编排","解析目标并生成唯一计划","先把目标变成可追踪对象，再从真正可执行能力交集中生成一次计划；运行中不重规划。",{"available_capabilities":list(handlers)},"model_inference+program_rule")
        response = await agent.handle(user_request=user_request,runtime_context=RuntimeContext(ACTOR,CHANNEL,"authenticated_session"),artifact_store=store)
        if response.status is not BusinessAgentStatus.COMPLETED or response.goal is None or response.plan is None: raise AssertionError(f"business run stopped: {response.status} {response.error or response.message}")
        steps = response.plan.steps
        if len(steps)!=2 or steps[0].capability_id!="directional_insight" or steps[1].capability_id!="customer_targeting" or steps[0].step_id not in steps[1].depends_on: raise AssertionError("single plan lacks direct two-act dependency")
        log.emit("编排","确认唯一计划","第二幕只能读取直接依赖步骤发布的 Opportunity。",{"goal":asdict(response.goal),"plan":asdict(response.plan)})
        context = response.execution_context; assert context is not None
        find = lambda prefix: next(ref for ref in context.published_artifacts if ref.startswith(prefix))
        opportunity = store.get(find("opportunity:")).value
        selection = store.get(find("selection_result:")).value
        customer_set = store.get(find("customer_set:")).value
        log.emit("第二幕","查询全量客户原始证据并调用机会评估模型","授权快照仅50人，可完整读取；保留负向、后续和跨主题上下文后逐客判断。",{"source":selection["fact_source"],"audit":selection["audit"],"tier_counts":{k:len(v) for k,v in selection["tiers"].items()},"excluded_count":len(selection["excluded"])},"source_fact+model_inference")
        log.emit("第二幕","执行发布前确定性校验","检查结构、引用、客户归属、逐字原文、时间覆盖和层级状态；这些检查不证明模型语义必然正确。",selection["validation"],"program_rule")
        priority = [x["customer_id"] for x in selection["tiers"]["priority"]]; handed = [x["customer_id"] for x in customer_set["customers"]]
        if not priority or priority != handed: raise AssertionError("handoff is not exactly the non-empty priority tier")
        featured = next(x for x in selection["tiers"]["priority"] if x["customer_id"]==selection["featured_customer_id"])
        if opportunity["data_source"]["version"] != selection["fact_source"]["version"]: raise AssertionError("snapshot version mismatch")
        log.emit("交付","发布三层名单与优先集合","展示保留三层；下游只接收有明确自身需求证据的优先沟通客户。",{"opportunity":opportunity,"tiers":{k:[concise(x) for x in v] for k,v in selection["tiers"].items()},"priority_customer_set":customer_set,"featured_customer":concise(featured)})
        log.emit("结束","确认本次运行边界","只完成发现机会与自动圈客；不生成产品匹配、策略、任务、成交概率或NBEV预测。",{"status":"COMPLETED","plan_count":1,"replan_count":0,"snapshot":opportunity["data_source"],"model":settings.model})
    finally: await model.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--request",default=REQUEST); args=parser.parse_args()
    try: asyncio.run(run(args.request)); return 0
    except Exception as exc: print(json.dumps({"status":"FAILED","error_type":type(exc).__name__,"error":str(exc)},ensure_ascii=False),flush=True); return 1
if __name__=="__main__": raise SystemExit(main())