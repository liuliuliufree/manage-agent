import asyncio
import json
import unittest
from datetime import datetime

from openai.types.chat import ChatCompletion

from src.application import CAPABILITY_CATALOG, Planner
from src.domain import Goal, PlanStatus
from src.model import FakeChatModel


def completion(content: str | dict[str, object]) -> ChatCompletion:
    response_content = (
        json.dumps(content, ensure_ascii=False)
        if isinstance(content, dict)
        else content
    )
    return ChatCompletion.model_validate(
        {
            "id": "planner-response",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": "fake-planner",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": response_content,
                    },
                }
            ],
        }
    )


def planner_for(*responses: str | dict[str, object]) -> tuple[Planner, FakeChatModel]:
    model = FakeChatModel(
        completions=tuple(completion(response) for response in responses)
    )
    return (
        Planner(
            model=model,
            model_name="fake-planner",
            plan_id_factory=lambda: "plan_test",
        ),
        model,
    )


def goal(request: str, goal_type: str) -> Goal:
    return Goal(
        goal_id="goal_test",
        version=2,
        original_request=request,
        goal_type=goal_type,
    )


class PlannerTests(unittest.TestCase):
    def test_opportunity_request_selects_only_directional_insight(self) -> None:
        planner, model = planner_for(
            {
                "steps": [
                    {
                        "step_id": "inspect_opportunities",
                        "capability_id": "directional_insight",
                        "depends_on": [],
                    }
                ]
            }
        )

        plan = asyncio.run(
            planner.plan(
                goal=goal("最近有什么值得关注的经营机会？", "opportunity_discovery"),
            )
        )

        self.assertEqual((plan.plan_id, plan.version), ("plan_test", 1))
        self.assertEqual(plan.status, PlanStatus.ACTIVE)
        self.assertEqual((plan.goal_ref.goal_id, plan.goal_ref.version), ("goal_test", 2))
        self.assertEqual(
            tuple(step.capability_id for step in plan.steps),
            ("directional_insight",),
        )
        request_text = json.dumps(model.requests[0], ensure_ascii=False, default=str)
        self.assertIn("最少合理能力", request_text)
        self.assertIn("没有固定执行顺序", request_text)
        for capability_id in CAPABILITY_CATALOG:
            self.assertIn(capability_id, request_text)

    def test_existing_opportunity_goes_directly_to_customer_targeting(self) -> None:
        planner, model = planner_for(
            {
                "steps": [
                    {
                        "step_id": "find_customers",
                        "capability_id": "customer_targeting",
                        "depends_on": [],
                    }
                ]
            }
        )
        context = {
            "opportunity_refs": ["opportunity_001"],
            "customer_refs": [],
            "strategy_refs": [],
            "task_refs": [],
        }

        plan = asyncio.run(
            planner.plan(
                goal=goal("围绕刚才这个机会找一批客户。", "customer_targeting"),
                context=context,
            )
        )

        self.assertEqual(
            tuple(step.capability_id for step in plan.steps),
            ("customer_targeting",),
        )
        request_text = json.dumps(model.requests[0], ensure_ascii=False, default=str)
        self.assertIn("opportunity_001", request_text)
        self.assertNotIn('"capability_id": "directional_insight"', request_text)

    def test_existing_customer_goes_directly_to_strategy_generation(self) -> None:
        planner, _ = planner_for(
            {
                "steps": [
                    {
                        "step_id": "prepare_strategy",
                        "capability_id": "strategy_generation",
                        "depends_on": [],
                    }
                ]
            }
        )

        plan = asyncio.run(
            planner.plan(
                goal=goal("王女士下一步怎么经营？", "strategy_advice"),
                context={"customer_refs": ["customer_wang"]},
            )
        )

        self.assertEqual(
            tuple(step.capability_id for step in plan.steps),
            ("strategy_generation",),
        )

    def test_tracking_request_selects_only_tracking_iteration(self) -> None:
        planner, _ = planner_for(
            {
                "steps": [
                    {
                        "step_id": "review_progress",
                        "capability_id": "tracking_iteration",
                        "depends_on": [],
                    }
                ]
            }
        )

        plan = asyncio.run(
            planner.plan(
                goal=goal("看看上周经营任务进展怎么样。", "task_tracking"),
                context={"task_refs": ["task_001"]},
            )
        )

        self.assertEqual(
            tuple(step.capability_id for step in plan.steps),
            ("tracking_iteration",),
        )

    def test_unknown_capability_is_rejected(self) -> None:
        planner, _ = planner_for(
            {
                "steps": [
                    {
                        "step_id": "invented",
                        "capability_id": "invented_capability",
                        "depends_on": [],
                    }
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "unknown capability"):
            asyncio.run(
                planner.plan(
                    goal=goal("帮我完成经营目标。", "performance_achievement"),
                )
            )

    def test_invalid_json_gets_one_format_repair(self) -> None:
        planner, model = planner_for(
            "```json\n{steps: []}\n```",
            {
                "steps": [
                    {
                        "step_id": "inspect_opportunities",
                        "capability_id": "directional_insight",
                        "depends_on": [],
                    }
                ]
            },
        )

        plan = asyncio.run(
            planner.plan(
                goal=goal("最近有什么经营机会？", "opportunity_discovery"),
            )
        )

        self.assertEqual(len(model.requests), 2)
        self.assertEqual(plan.steps[0].capability_id, "directional_insight")
        repair_request = json.dumps(model.requests[1], ensure_ascii=False, default=str)
        self.assertIn("只修复 JSON 格式", repair_request)


if __name__ == "__main__":
    unittest.main()
