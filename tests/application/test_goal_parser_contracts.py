import asyncio
import json
import unittest
from decimal import Decimal

from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from src.application import BusinessAgent, BusinessAgentStatus, CapabilityExecutor, GoalParseStatus, GoalParser, RuntimeContext
from src.model import FakeChatModel


def completion(payload: object) -> ChatCompletion:
    return ChatCompletion(
        id="test", created=0, model="test", object="chat.completion",
        choices=[Choice(index=0, finish_reason="stop", message=ChatCompletionMessage(role="assistant", content=payload if isinstance(payload, str) else json.dumps(payload)))],
    )


def new_goal_payload(**extra: object) -> dict[str, object]:
    result: dict[str, object] = {
        "goal_type": "performance_achievement",
        "metric": {"code": "invented_metric"},
        "target": {"value": 500, "unit": "万元", "direction": "at_least"},
        "needs_clarification": False,
    }
    result.update(extra)
    return result


class GoalParserContractTests(unittest.TestCase):
    def parse(self, payloads: list[object], request: str = "本月NBEV目标500W"):
        model = FakeChatModel(completions=[completion(payload) for payload in payloads])
        parser = GoalParser(model=model, model_name="test", goal_id_factory=lambda: "goal-stable")
        return asyncio.run(parser.parse(user_request=request, runtime_context=RuntimeContext("agent-a", "individual"))), model, parser

    def test_creation_uses_stable_identity_trusted_context_and_vocabulary(self) -> None:
        result, _, _ = self.parse([new_goal_payload(actor="evil", channel="bank")])
        self.assertEqual(result.status, GoalParseStatus.READY)
        self.assertEqual((result.goal.goal_id, result.goal.version), ("goal-stable", 1))  # type: ignore[union-attr]
        self.assertEqual(result.goal.metric.code, "nbev")  # type: ignore[union-attr]
        self.assertEqual(result.goal.channel_and_actor.actor_id, "agent-a")  # type: ignore[union-attr]

    def test_ambiguous_metric_is_structured_and_blocks_planner(self) -> None:
        parsed, _, _ = self.parse([new_goal_payload()], "本月业绩目标500W")
        self.assertEqual(parsed.status, GoalParseStatus.CLARIFICATION_REQUIRED)
        self.assertEqual(parsed.missing_information[0].field, "metric")
        self.assertTrue(parsed.goal.missing_information[0].required_before_execution)  # type: ignore[union-attr]

        class PlannerMustNotRun:
            async def plan(self, **kwargs):
                raise AssertionError("Planner must not run for a blocking Goal")

        parser_for_agent = GoalParser(model=FakeChatModel(completions=[completion(new_goal_payload())]), model_name="test")
        response = asyncio.run(BusinessAgent(goal_parser=parser_for_agent, planner=PlannerMustNotRun(), capability_executor=CapabilityExecutor({})).handle(user_request="本月业绩目标500W"))
        self.assertEqual(response.status, BusinessAgentStatus.CLARIFICATION_REQUIRED)

    def test_set_keep_clear_and_original_request_are_unambiguous(self) -> None:
        initial, _, parser = self.parse([new_goal_payload(product_or_need_context={"products": ["产品甲"], "needs": [], "raw_expression": "产品甲"})], "本月NBEV目标500W，主推产品甲")
        model = FakeChatModel(completions=[completion({"updates": {"target": {"op": "SET", "value": {"value": 400, "unit": "万元"}}, "product_or_need_context": {"op": "KEEP"}, "metric": {"op": "KEEP"}}, "needs_clarification": False})])
        parser = GoalParser(model=model, model_name="test")
        revised = asyncio.run(parser.parse(user_request="目标改成400W", existing_goal=initial.goal))
        self.assertEqual(revised.goal.version, 2)  # type: ignore[union-attr]
        self.assertEqual(revised.goal.original_request, initial.goal.original_request)  # type: ignore[union-attr]
        self.assertEqual(revised.goal.target.value, Decimal("400"))  # type: ignore[union-attr]
        self.assertEqual(revised.goal.product_or_need_context.products, ("产品甲",))  # type: ignore[union-attr]
        self.assertEqual(initial.goal.target.value, Decimal("500"))  # type: ignore[union-attr]

        clearer = FakeChatModel(completions=[completion({"updates": {"product_or_need_context": {"op": "CLEAR"}}, "needs_clarification": False})])
        cleared = asyncio.run(GoalParser(model=clearer, model_name="test").parse(user_request="不再主推产品甲，删除产品方向", existing_goal=revised.goal))
        self.assertIsNone(cleared.goal.product_or_need_context)  # type: ignore[union-attr]

    def test_invented_fields_are_rejected_and_json_repair_is_single_attempt(self) -> None:
        result, model, _ = self.parse(["{not json", new_goal_payload(product_or_need_context={"products": ["幻觉产品"], "needs": [], "raw_expression": "幻觉产品"})])
        self.assertEqual(len(model.requests), 2)
        self.assertIsNone(result.goal.product_or_need_context)  # type: ignore[union-attr]

        failed, failed_model, _ = self.parse(["{bad", "still bad"])
        self.assertEqual(failed.status, GoalParseStatus.TECHNICAL_FAILURE)
        self.assertEqual(len(failed_model.requests), 2)


if __name__ == "__main__":
    unittest.main()
