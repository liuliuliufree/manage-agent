import asyncio
import json
import sys
import unittest
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from openai.types.chat import ChatCompletion

from src.application import GoalParser, RuntimeContext
from src.domain import (
    ChannelAndActor,
    Goal,
    Metric,
    ProductOrNeedContext,
    Target,
    TimeHorizon,
)
from src.model import FakeChatModel


def completion(payload: dict[str, object]) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "goal-parser-response",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": "fake-goal-parser",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                }
            ],
        }
    )


def parser_for(payload: dict[str, object]) -> tuple[GoalParser, FakeChatModel]:
    model = FakeChatModel(completions=(completion(payload),))
    return (
        GoalParser(
            model=model,
            model_name="fake-goal-parser",
            goal_id_factory=lambda: "goal_test",
        ),
        model,
    )


def print_case(
    *,
    user_question: str,
    llm_json: dict[str, object],
    result: object,
) -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    llm_text = json.dumps(llm_json, ensure_ascii=False, indent=2)
    result_text = json.dumps(
        asdict(result),
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    print(
        "\n=== Goal Parser Case ===\n"
        f"User question:\n{user_question}\n"
        f"LLM JSON:\n{llm_text}\n"
        f"Python processed JSON:\n{result_text}",
        flush=True,
    )


class GoalParserTests(unittest.TestCase):
    def test_parses_performance_goal_and_applies_trusted_runtime_context(self) -> None:
        user_request = "开门红阶段完成500W NBEV，主推御享分红26和御享金越年金。"
        llm_json: dict[str, object] = {
            "goal_type": "performance_achievement",
            "metric": {"code": "NBEV", "display_name": "新业务价值"},
            "target": {
                "target_type": "value",
                "value": 500,
                "unit": "万元",
                "direction": "at_least",
            },
            "time_horizon": {
                "raw_expression": "开门红阶段",
                "start_at": "2026-01-01",
                "end_at": "2026-03-31",
            },
            "product_mentions": ["御享分红26", "御享金越年金"],
            "actor_ref": "model_invented_actor",
            "channel_ref": "model_invented_channel",
            "needs_clarification": False,
            "clarification_question": None,
        }
        parser, model = parser_for(llm_json)

        result = asyncio.run(
            parser.parse(
                user_request=user_request,
                runtime_context=RuntimeContext(
                    actor_ref="agent_001",
                    channel_ref="individual_insurance",
                ),
            )
        )
        print_case(
            user_question=user_request,
            llm_json=llm_json,
            result=result,
        )

        self.assertFalse(result.need_clarification)
        self.assertIsNotNone(result.goal)
        goal = result.goal
        assert goal is not None
        self.assertEqual((goal.goal_id, goal.version), ("goal_test", 1))
        self.assertEqual(goal.original_request, user_request)
        self.assertEqual(goal.goal_type, "performance_achievement")
        self.assertEqual(goal.metric, Metric("NBEV", "新业务价值"))
        self.assertEqual(
            goal.target,
            Target(Decimal("500"), "万元", "at_least"),
        )
        self.assertEqual(
            goal.time_horizon,
            TimeHorizon(raw_expression="开门红阶段"),
        )
        self.assertEqual(
            goal.product_or_need_context,
            ProductOrNeedContext(
                products=("御享分红26", "御享金越年金"),
                raw_expression="主推御享分红26和御享金越年金",
            ),
        )
        self.assertEqual(
            goal.channel_and_actor,
            ChannelAndActor(
                actor_id="agent_001",
                channel_id="individual_insurance",
                context_source="runtime_context",
            ),
        )
        request = model.requests[0]
        request_text = json.dumps(request, ensure_ascii=False)
        self.assertNotIn("agent_001", request_text)
        self.assertNotIn("individual_insurance", request_text)

    def test_ambiguous_metric_requires_clarification(self) -> None:
        user_request = "这个月业绩做到500W。"
        llm_json: dict[str, object] = {
            "goal_type": "performance_achievement",
            "metric": None,
            "target": {
                "target_type": "numeric",
                "value": 500,
                "unit": "万元",
                "direction": "at_least",
            },
            "needs_clarification": True,
            "clarification_question": "这里的500W具体指NBEV、保费还是其他指标？",
        }
        parser, _ = parser_for(llm_json)

        result = asyncio.run(
            parser.parse(
                user_request=user_request,
                runtime_context=RuntimeContext("agent_001", "individual_insurance"),
            )
        )
        print_case(
            user_question=user_request,
            llm_json=llm_json,
            result=result,
        )

        self.assertTrue(result.need_clarification)
        self.assertTrue(result.needs_clarification)
        self.assertIsNone(result.goal)
        self.assertEqual(
            result.clarification_question,
            "这里的500W具体指NBEV、保费还是其他指标？",
        )

    def test_generic_performance_metric_overrides_model_invented_code(self) -> None:
        parser, _ = parser_for(
            {
                "goal_type": "performance_achievement",
                "metric": {
                    "code": "test_performance",
                    "display_name": "测试业绩",
                },
                "target": {
                    "target_type": "amount",
                    "value": 500,
                    "unit": "万元",
                    "direction": "at_least",
                },
                "needs_clarification": False,
                "clarification_question": None,
            }
        )

        result = asyncio.run(
            parser.parse(user_request="这个月测试业绩做到500W。")
        )

        self.assertTrue(result.need_clarification)
        self.assertIsNone(result.goal)
        self.assertIn("具体指", result.clarification_question)

    def test_model_inferred_need_is_not_promoted_to_goal_fact(self) -> None:
        user_request = "看看50岁客户。"
        llm_json: dict[str, object] = {
            "goal_type": "customer_operation",
            "audience_scope": {
                "scope_type": "described_customers",
                "scope_reference": None,
                "raw_expression": "50岁客户",
            },
            "product_mentions": [],
            "need_mentions": ["养老需求"],
            "product_or_need_raw_expression": "养老需求",
            "needs_clarification": False,
            "clarification_question": None,
        }
        parser, _ = parser_for(llm_json)

        result = asyncio.run(parser.parse(user_request=user_request))
        print_case(
            user_question=user_request,
            llm_json=llm_json,
            result=result,
        )

        self.assertIsNotNone(result.goal)
        goal = result.goal
        assert goal is not None
        self.assertIsNone(goal.product_or_need_context)
        self.assertEqual(goal.audience_scope.raw_expression, "50岁客户")

    def test_existing_goal_patch_preserves_unmodified_business_fields(self) -> None:
        user_request = "改成400W。"
        existing = Goal(
            goal_id="goal_existing",
            version=1,
            original_request="完成500W NBEV，主推产品A和产品B。",
            goal_type="performance_achievement",
            metric=Metric("NBEV", "新业务价值"),
            target=Target(Decimal("500"), "万元"),
            time_horizon=TimeHorizon(raw_expression="本阶段"),
            product_or_need_context=ProductOrNeedContext(
                products=("产品A", "产品B"),
                raw_expression="主推产品A和产品B",
            ),
            channel_and_actor=ChannelAndActor(
                actor_id="agent_old",
                channel_id="individual_insurance",
                context_source="runtime_context",
            ),
        )
        llm_json: dict[str, object] = {
            "target": {
                "target_type": "numeric",
                "value": 400,
                "unit": "万元",
                "direction": "at_least",
            },
            "needs_clarification": False,
            "clarification_question": None,
        }
        parser, _ = parser_for(llm_json)

        result = asyncio.run(
            parser.parse(
                user_request=user_request,
                runtime_context=RuntimeContext(
                    actor_ref="agent_001",
                    channel_ref="individual_insurance",
                ),
                existing_goal=existing,
            )
        )
        print_case(
            user_question=user_request,
            llm_json=llm_json,
            result=result,
        )

        self.assertIsNotNone(result.goal)
        revised = result.goal
        assert revised is not None
        self.assertEqual((revised.goal_id, revised.version), ("goal_existing", 2))
        self.assertEqual(revised.metric, existing.metric)
        self.assertEqual(
            revised.product_or_need_context,
            existing.product_or_need_context,
        )
        self.assertEqual(revised.target.value, Decimal("400"))
        self.assertEqual(revised.channel_and_actor.actor_id, "agent_001")

    def test_prompt_allows_relative_reference_to_existing_opportunity(self) -> None:
        user_request = "围绕刚才这个机会找一批客户。"
        parser, model = parser_for(
            {
                "goal_type": "customer_targeting",
                "needs_clarification": False,
                "clarification_question": None,
            }
        )

        result = asyncio.run(parser.parse(user_request=user_request))

        self.assertFalse(result.need_clarification)
        self.assertEqual(result.goal.goal_type, "customer_targeting")
        request_text = json.dumps(model.requests[0], ensure_ascii=False)
        self.assertIn("刚才的机会", request_text)
        self.assertIn("不得因为模型看不到该 Context", request_text)


if __name__ == "__main__":
    unittest.main()
