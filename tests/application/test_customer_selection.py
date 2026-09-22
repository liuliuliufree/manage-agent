import json
import unittest
from pathlib import Path

from openai.types.chat import ChatCompletion

from src.application.customer_selection import (
    CUSTOMER_TARGETING_IO,
    CustomerSelectionConfig,
    build_customer_selection_tools,
    make_customer_targeting_handler,
)
from src.application.insight_tools import InsightToolConfig
from src.application import ArtifactStore
from src.domain import (
    ActorContext,
    CapabilityRequest,
    CapabilityStatus,
    GoalRef,
    PlanRef,
)
from src.model import FakeChatModel


ROOT = Path(__file__).resolve().parents[2]


def completion(payload, *, raw=False):
    content = payload if raw else json.dumps(payload, ensure_ascii=False)
    return ChatCompletion.model_validate({
        "id": "chatcmpl-selection",
        "choices": [{"finish_reason": "stop", "index": 0, "message": {"role": "assistant", "content": content}}],
        "created": 0,
        "model": "fake-selection",
        "object": "chat.completion",
    })


def assessment(customer_id):
    result = {
        "customer_id": customer_id,
        "opportunity_relevance": "uncertain",
        "need_state": "insufficient",
        "supporting_evidence": [],
        "limiting_evidence": [],
        "contradicting_evidence": [],
        "need_summary": None,
        "suggested_tier": None,
        "reason": "现有记录不足以判断本次机会。",
        "information_to_verify": [],
    }
    cases = {
        "C001": {
            "opportunity_relevance": "related", "need_state": "attention_only", "suggested_tier": "continued",
            "supporting_evidence": [{"event_id": "EVT_C001_01", "quote": "退休后收入来源有哪些"}],
            "reason": "只有相关浏览信号。",
        },
        "C021": {
            "opportunity_relevance": "related", "need_state": "explicit_self_need", "suggested_tier": "priority",
            "supporting_evidence": [{"event_id": "EVT_C021_03", "quote": "给自己安排一份退休后的补充收入"}],
            "need_summary": "希望为自己安排退休后的补充收入。", "reason": "明确表达自身相关需求。",
            "information_to_verify": ["领取开始时间"],
        },
        "C022": {
            "opportunity_relevance": "related", "need_state": "explicit_self_need", "suggested_tier": "priority",
            "supporting_evidence": [{"event_id": "EVT_C022_03", "quote": "为自己未来退休后的生活准备一份补充收入"}],
            "limiting_evidence": [{"event_id": "EVT_C022_04", "quote": "医疗保障这件事我近期暂不考虑"}],
            "need_summary": "希望为自己准备退休补充收入。", "reason": "自身需求明确；较晚否定是无关主题。",
            "information_to_verify": ["领取时间"],
        },
        "C023": {
            "opportunity_relevance": "related", "need_state": "active_inquiry", "suggested_tier": "further",
            "supporting_evidence": [{"event_id": "EVT_C023_03", "quote": "只是想弄清楚领取规则"}],
            "reason": "主动咨询但尚未确认自身安排。",
        },
        "C024": {
            "opportunity_relevance": "related", "need_state": "other_person", "suggested_tier": None,
            "limiting_evidence": [{"event_id": "EVT_C024_03", "quote": "替朋友问问"}],
            "reason": "需求主体不是当前客户。",
        },
        "C025": {
            "opportunity_relevance": "related", "need_state": "current_negative", "suggested_tier": None,
            "supporting_evidence": [{"event_id": "EVT_C025_03", "quote": "为自己未来退休后的生活准备一份补充收入"}],
            "contradicting_evidence": [{"event_id": "EVT_C025_04", "quote": "今年先暂不考虑了"}],
            "reason": "同主题较晚记录已撤回。",
        },
    }
    result.update(cases.get(customer_id, {}))
    return result


def assessments(*, mutate=None):
    values = [assessment(f"C{index:03d}") for index in range(1, 51)]
    if mutate:
        mutate(values)
    return {"assessments": values}


class CustomerSelectionTests(unittest.TestCase):
    def config(self):
        return CustomerSelectionConfig(
            insight=InsightToolConfig.from_repository(ROOT),
            actor_id="AGENT_DEMO_001",
            channel_id="individual",
        )

    def request(self):
        return CapabilityRequest(
            request_id="request-selection-1",
            capability_id="customer_targeting",
            goal_ref=GoalRef("goal-1", 1),
            plan_ref=PlanRef("plan-1", 1),
            actor_context=ActorContext("AGENT_DEMO_001", "individual", "test-runtime"),
            input_refs=("opportunity:opp-1",),
        )

    def store(self):
        store = ArtifactStore()
        store.put("opportunity", "opp-1", {
            "opportunity_id": "opp-1",
            "goal_ref": {"goal_id": "goal-1", "version": 1},
            "opportunity_type": "retirement_income_planning",
            "problem_statement": "识别退休后补充收入安排的沟通机会",
            "evidence_scope": {"topic_codes": ["retirement_income"]},
            "evidence_links": [{"evidence_id": "synthetic-upstream", "role": "supports"}],
            "data_source": {"dataset_id": "insight_demo_v2", "version": "2.0", "synthetic": True},
            "integration_boundary": "synthetic_upstream_opportunity",
        })
        return store

    def test_query_preserves_complete_negative_and_cross_topic_context(self):
        tool, _ = build_customer_selection_tools(
            self.config(), model=FakeChatModel(), artifact_resolver=lambda ref: {},
        )
        result = tool.handler({"customer_ids": ["C022", "C025", "C046"]})
        self.assertEqual(result["status"], "ok")
        packages = {item["customer"]["customer_id"]: item for item in result["data"]["customers"]}
        self.assertEqual([event["event_id"] for event in packages["C025"]["recent_events"]][-2:], ["EVT_C025_03", "EVT_C025_04"])
        self.assertEqual(packages["C022"]["recent_events"][-1]["topic_code"], "health_protection")
        self.assertEqual(packages["C046"]["recent_events"], [])
        self.assertTrue(packages["C046"]["coverage"]["history_is_sparse"])
        self.assertEqual(result["sources"][0]["dataset_id"], "insight_demo_v2")
        self.assertEqual(result["sources"][0]["version"], "2.0")

    def test_capability_publishes_three_tiers_and_priority_only_handoff(self):
        store = self.store()
        model = FakeChatModel(completions=[completion(assessments())])
        handler = make_customer_targeting_handler(self.config(), model=model, artifact_store=store)
        result = handler(self.request())
        self.assertIs(result.status, CapabilityStatus.SUCCESS)
        self.assertEqual(CUSTOMER_TARGETING_IO.required_inputs, ("opportunity",))
        self.assertEqual({item.output_type for item in result.outputs}, {"selection_result", "customer_set"})
        selection = store.get(next(f"selection_result:{item.output_id}" for item in result.outputs if item.output_type == "selection_result")).value
        handoff = store.get(next(f"customer_set:{item.output_id}" for item in result.outputs if item.output_type == "customer_set")).value
        self.assertEqual([item["customer_id"] for item in selection["tiers"]["priority"]], ["C021", "C022"])
        self.assertEqual([item["customer_id"] for item in selection["tiers"]["further"]], ["C023"])
        self.assertEqual([item["customer_id"] for item in selection["tiers"]["continued"]], ["C001"])
        self.assertEqual([item["customer_id"] for item in handoff["customers"]], ["C021", "C022"])
        self.assertIn(selection["featured_customer_id"], {"C021", "C022"})
        prompt = model.requests[0]["messages"][1]["content"]
        self.assertNotIn("statement_kind", prompt)
        self.assertNotIn("customer_selection_semantics_v2", prompt)
        self.assertEqual(len(model.requests), 1)

    def test_forged_or_cross_customer_reference_cannot_publish(self):
        def mutate(values):
            item = next(value for value in values if value["customer_id"] == "C021")
            item["supporting_evidence"] = [{"event_id": "EVT_C022_03", "quote": "为自己未来退休后的生活准备一份补充收入"}]

        store = self.store()
        handler = make_customer_targeting_handler(
            self.config(), model=FakeChatModel(completions=[completion(assessments(mutate=mutate))]), artifact_store=store,
        )
        result = handler(self.request())
        self.assertIs(result.status, CapabilityStatus.FAILED)
        self.assertEqual(result.errors[0].code, "CUSTOMER_ASSESSMENT_INVALID")
        self.assertFalse(any(item.output_type in {"selection_result", "customer_set"} for item in result.outputs))

    def test_general_question_and_same_topic_withdrawal_cannot_be_forced_into_priority(self):
        def force_general(values):
            item = next(value for value in values if value["customer_id"] == "C023")
            item.update(need_state="explicit_self_need", suggested_tier="priority")

        store = self.store()
        result = make_customer_targeting_handler(
            self.config(), model=FakeChatModel(completions=[completion(assessments(mutate=force_general))]), artifact_store=store,
        )(self.request())
        self.assertIs(result.status, CapabilityStatus.FAILED)
        self.assertIn("general question", result.errors[0].message)

        def ignore_withdrawal(values):
            item = next(value for value in values if value["customer_id"] == "C025")
            item.update(need_state="explicit_self_need", suggested_tier="priority", contradicting_evidence=[])

        store = self.store()
        result = make_customer_targeting_handler(
            self.config(), model=FakeChatModel(completions=[completion(assessments(mutate=ignore_withdrawal))]), artifact_store=store,
        )(self.request())
        self.assertIs(result.status, CapabilityStatus.FAILED)
        self.assertIn("later same-topic", result.errors[0].message)

    def test_model_error_and_invalid_protocol_stop_without_outputs(self):
        for payload, raw, code in [('{"assessments":', True, "MODEL_PROTOCOL_INVALID"), ({"wrong": []}, False, "MODEL_PROTOCOL_INVALID")]:
            with self.subTest(payload=payload):
                store = self.store()
                result = make_customer_targeting_handler(
                    self.config(), model=FakeChatModel(completions=[completion(payload, raw=raw)]), artifact_store=store,
                )(self.request())
                self.assertIs(result.status, CapabilityStatus.FAILED)
                self.assertEqual(result.errors[0].code, code)
                self.assertEqual(result.outputs, ())

    def test_snapshot_actor_or_version_mismatch_is_rejected(self):
        bad = CustomerSelectionConfig(
            insight=InsightToolConfig.from_repository(ROOT), actor_id="OTHER", channel_id="individual"
        )
        tool, _ = build_customer_selection_tools(bad, model=FakeChatModel(), artifact_resolver=lambda ref: {})
        self.assertEqual(tool.handler({})["error"]["code"], "RESOURCE_FORBIDDEN")


if __name__ == "__main__":
    unittest.main()