import json
import unittest
from decimal import Decimal

from openai.types.chat import ChatCompletion

from src.application.goal_parser import (
    GoalParseStatus,
    GoalParser,
    MetricVocabulary,
    RuntimeContext,
)
from src.domain import ChannelAndActor, Goal
from src.model import FakeChatModel


def completion(payload: object, *, raw: bool = False) -> ChatCompletion:
    content = payload if raw else json.dumps(payload, ensure_ascii=False)
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "created": 0,
            "model": "fake",
            "object": "chat.completion",
        }
    )


def payload(
    *,
    goal_type="performance_achievement",
    metric_text="NBEV",
    target_text="500W",
    time_text=None,
    products=None,
    needs=None,
    audience_text=None,
    constraints=None,
):
    return {
        "goal_type": goal_type,
        "metric_text": metric_text,
        "target_text": target_text,
        "time_text": time_text,
        "products": products or [],
        "needs": needs or [],
        "audience_text": audience_text,
        "constraints": constraints or [],
    }


RUNTIME = RuntimeContext("agent-7", "individual", "demo_runtime")


class GoalParserDemoV1Tests(unittest.IsolatedAsyncioTestCase):
    async def parse(self, request: str, model_payload: object):
        model = FakeChatModel(completions=[completion(model_payload)])
        parser = GoalParser(
            model=model,
            model_name="fake",
            goal_id_factory=lambda: "goal-1",
        )
        return await parser.parse(user_request=request, runtime_context=RUNTIME), model

    async def test_complete_goal_uses_grounded_text_and_trusted_runtime(self):
        request = "开门红目标500W NBEV，主推御享分红26和御享金越年金"
        result, model = await self.parse(
            request,
            payload(
                time_text="开门红",
                products=["御享分红26", "御享金越年金"],
            ),
        )

        self.assertIs(result.status, GoalParseStatus.SUCCESS)
        self.assertEqual(result.goal.goal_id, "goal-1")
        self.assertEqual(result.goal.version, 1)
        self.assertEqual(result.goal.original_request, request)
        self.assertEqual(result.goal.metric.code, "nbev")
        self.assertEqual(result.goal.target.value, Decimal("5000000"))
        self.assertEqual(result.goal.target.unit, "元")
        self.assertEqual(result.goal.time_horizon.raw_expression, "开门红")
        self.assertEqual(
            result.goal.product_or_need_context.products,
            ("御享分红26", "御享金越年金"),
        )
        self.assertEqual(result.goal.channel_and_actor.actor_id, "agent-7")
        self.assertEqual(len(model.requests), 1)
        messages = model.requests[0]["messages"]
        self.assertNotIn("agent-7", json.dumps(messages, ensure_ascii=False))
        self.assertNotIn("individual", json.dumps(messages, ensure_ascii=False))

    async def test_replacement_stage_product_and_amount_need_no_code_change(self):
        request = "下半年目标300万元NBEV，主推产品甲"
        result, _ = await self.parse(
            request,
            payload(
                target_text="300万元",
                time_text="下半年",
                products=["产品甲"],
            ),
        )
        self.assertIs(result.status, GoalParseStatus.SUCCESS)
        self.assertEqual(result.goal.target.value, Decimal("3000000"))
        self.assertEqual(result.goal.product_or_need_context.products, ("产品甲",))

    async def test_opportunity_discovery_needs_no_metric_or_target(self):
        result, _ = await self.parse(
            "帮我发现近期经营机会",
            payload(
                goal_type="opportunity_discovery",
                metric_text=None,
                target_text=None,
                time_text="近期",
            ),
        )
        self.assertIs(result.status, GoalParseStatus.SUCCESS)
        self.assertIsNone(result.goal.metric)
        self.assertIsNone(result.goal.target)

    async def test_unknown_metric_returns_partial_goal_and_structured_missing(self):
        result, _ = await self.parse(
            "这个月业绩做到500W",
            payload(metric_text="业绩", time_text="这个月"),
        )
        self.assertIs(result.status, GoalParseStatus.CLARIFICATION_REQUIRED)
        self.assertIsNotNone(result.goal)
        self.assertIsNone(result.goal.metric)
        self.assertEqual(result.goal.target.value, Decimal("5000000"))
        self.assertEqual(result.missing_information, result.goal.missing_information)
        self.assertEqual(result.missing_information[0].field, "metric")
        self.assertTrue(result.missing_information[0].required_before_execution)

    async def test_supported_amount_forms_and_unsupported_forms(self):
        cases = [
            ("目标500W NBEV", "500W", Decimal("5000000"), False),
            ("目标500万元 NBEV", "500万元", Decimal("5000000"), False),
            ("目标0.05亿元 NBEV", "0.05亿元", Decimal("5000000"), False),
            ("目标0W NBEV", "0W", None, True),
            ("目标-1W NBEV", "-1W", None, True),
            ("目标100到500W NBEV", "100到500W", None, True),
            ("目标不超过500W NBEV", "不超过500W", None, True),
        ]
        for request, target_text, expected, clarifies in cases:
            with self.subTest(request=request):
                result, _ = await self.parse(
                    request,
                    payload(target_text=target_text),
                )
                self.assertEqual(
                    result.status is GoalParseStatus.CLARIFICATION_REQUIRED,
                    clarifies,
                )
                if expected is not None:
                    self.assertEqual(result.goal.target.value, expected)

    async def test_ungrounded_content_fails_as_a_whole(self):
        result, model = await self.parse(
            "目标500W NBEV",
            payload(products=["模型臆造产品"]),
        )
        self.assertIs(result.status, GoalParseStatus.TECHNICAL_FAILURE)
        self.assertEqual(result.error, "MODEL_GROUNDING_FAILED")
        self.assertIsNone(result.goal)
        self.assertEqual(len(model.requests), 1)

    async def test_extra_identity_field_is_protocol_failure_without_repair(self):
        invalid = payload()
        invalid["actor"] = "model-actor"
        result, model = await self.parse("目标500W NBEV", invalid)
        self.assertEqual(result.error, "MODEL_PROTOCOL_INVALID")
        self.assertEqual(len(model.requests), 1)

    async def test_runtime_is_required_before_model_call(self):
        model = FakeChatModel(completions=[completion(payload())])
        parser = GoalParser(model=model, model_name="fake")
        result = await parser.parse(user_request="目标500W NBEV")
        self.assertEqual(result.error, "RUNTIME_CONTEXT_REQUIRED")
        self.assertEqual(model.requests, [])

    async def test_malformed_and_wrong_shape_are_not_repaired(self):
        for model_output in ["```json\n{}\n```", "[]", '{"goal_type":']:
            with self.subTest(model_output=model_output):
                model = FakeChatModel(completions=[completion(model_output, raw=True)])
                parser = GoalParser(model=model, model_name="fake")
                result = await parser.parse(
                    user_request="目标500W NBEV", runtime_context=RUNTIME
                )
                self.assertEqual(result.error, "MODEL_PROTOCOL_INVALID")
                self.assertEqual(len(model.requests), 1)

    async def test_model_exception_is_hidden(self):
        class FailingModel:
            requests = []

            async def complete(self, request):
                self.requests.append(request)
                raise RuntimeError("secret-token-value")

        parser = GoalParser(model=FailingModel(), model_name="fake")
        result = await parser.parse(
            user_request="目标500W NBEV", runtime_context=RUNTIME
        )
        self.assertEqual(result.error, "MODEL_CALL_FAILED")
        self.assertNotIn("secret", result.error)

    async def test_existing_goal_is_not_revised_or_sent_to_model(self):
        existing = Goal(
            goal_id="old",
            version=1,
            original_request="旧目标",
            goal_type="opportunity_discovery",
            channel_and_actor=ChannelAndActor("individual", "agent-7", "trusted"),
        )
        model = FakeChatModel(completions=[completion(payload())])
        parser = GoalParser(model=model, model_name="fake")
        result = await parser.parse(
            user_request="改成400W",
            runtime_context=RUNTIME,
            existing_goal=existing,
        )
        self.assertIs(result.status, GoalParseStatus.CLARIFICATION_REQUIRED)
        self.assertIsNone(result.goal)
        self.assertEqual(existing.version, 1)
        self.assertEqual(model.requests, [])

    async def test_empty_or_null_goal_type_clarifies_without_goal(self):
        model = FakeChatModel(
            completions=[
                completion(
                    payload(
                        goal_type=None,
                        metric_text=None,
                        target_text=None,
                    )
                )
            ]
        )
        parser = GoalParser(model=model, model_name="fake")
        empty = await parser.parse(user_request=" ", runtime_context=RUNTIME)
        unsupported = await parser.parse(
            user_request="给客户张三直接发消息", runtime_context=RUNTIME
        )
        self.assertIs(empty.status, GoalParseStatus.CLARIFICATION_REQUIRED)
        self.assertIsNone(empty.goal)
        self.assertIs(unsupported.status, GoalParseStatus.CLARIFICATION_REQUIRED)
        self.assertIsNone(unsupported.goal)
        self.assertEqual(len(model.requests), 1)

    async def test_invalid_metric_configuration_has_no_hardcoded_fallback(self):
        vocabulary = MetricVocabulary(data={"source_id": "", "version": "", "metrics": []})
        model = FakeChatModel(completions=[completion(payload())])
        parser = GoalParser(
            model=model,
            model_name="fake",
            metric_vocabulary=vocabulary,
        )
        result = await parser.parse(
            user_request="目标500W NBEV", runtime_context=RUNTIME
        )
        self.assertEqual(result.error, "METRIC_CONFIG_INVALID")
        self.assertEqual(model.requests, [])


if __name__ == "__main__":
    unittest.main()
