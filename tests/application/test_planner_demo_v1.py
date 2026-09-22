import json
import unittest

from openai.types.chat import ChatCompletion

from src.application.planner.planner import (
    Planner,
    PlannerError,
    PlanningUnavailableError,
)
from src.domain import ChannelAndActor, Goal, PlanStatus
from src.model import FakeChatModel


def completion(content: object, *, raw: bool = False) -> ChatCompletion:
    text = content if raw else json.dumps(content, ensure_ascii=False)
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-planner",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                }
            ],
            "created": 0,
            "model": "fake",
            "object": "chat.completion",
        }
    )


def goal() -> Goal:
    return Goal(
        goal_id="goal-1",
        version=1,
        original_request="发现经营机会",
        goal_type="opportunity_discovery",
        channel_and_actor=ChannelAndActor("individual", "agent-1", "demo_runtime"),
    )


CATALOG = {
    "directional_insight": {"description": "机会"},
    "customer_targeting": {"description": "圈客"},
    "strategy_generation": {"description": "策略"},
}


class PlannerDemoV1Tests(unittest.IsolatedAsyncioTestCase):
    async def planner(self, outputs):
        model = FakeChatModel(completions=[completion(item, raw=isinstance(item, str)) for item in outputs])
        return (
            Planner(model=model, model_name="fake", plan_id_factory=lambda: "plan-1"),
            model,
        )

    async def test_single_capability_plan_identity_is_application_controlled(self):
        planner, model = await self.planner(
            [{"steps": [{"step_id": "inspect", "capability_id": "directional_insight", "depends_on": []}]}]
        )
        result = await planner.plan(goal=goal(), capability_catalog=CATALOG)
        self.assertEqual(result.plan_id, "plan-1")
        self.assertEqual(result.version, 1)
        self.assertEqual(result.goal_ref.goal_id, "goal-1")
        self.assertIs(result.status, PlanStatus.ACTIVE)
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(len(model.requests), 1)

    async def test_context_is_copied_and_model_may_skip_prior_capabilities(self):
        planner, model = await self.planner(
            [{"steps": [{"step_id": "write", "capability_id": "strategy_generation", "depends_on": []}]}]
        )
        context = {"opportunity_refs": ["opp-1"], "customer_refs": ["set-1"]}
        await planner.plan(goal=goal(), context=context, capability_catalog=CATALOG)
        sent = json.loads(model.requests[0]["messages"][1]["content"])
        self.assertEqual(sent["existing_context"], context)
        self.assertEqual(context["opportunity_refs"], ["opp-1"])

    async def test_repeated_capability_with_distinct_steps_is_valid(self):
        planner, _ = await self.planner(
            [
                {
                    "steps": [
                        {"step_id": "inspect_a", "capability_id": "directional_insight", "depends_on": []},
                        {"step_id": "inspect_b", "capability_id": "directional_insight", "depends_on": []},
                    ]
                }
            ]
        )
        result = await planner.plan(goal=goal(), capability_catalog=CATALOG)
        self.assertEqual(len(result.steps), 2)

    async def test_invalid_plan_graph_or_capability_is_plan_invalid_without_retry(self):
        cases = [
            [{"step_id": "x", "capability_id": "unknown", "depends_on": []}],
            [
                {"step_id": "x", "capability_id": "directional_insight", "depends_on": []},
                {"step_id": "x", "capability_id": "customer_targeting", "depends_on": []},
            ],
            [{"step_id": "x", "capability_id": "directional_insight", "depends_on": ["missing"]}],
            [{"step_id": "x", "capability_id": "directional_insight", "depends_on": ["x"]}],
            [
                {"step_id": "x", "capability_id": "directional_insight", "depends_on": ["y"]},
                {"step_id": "y", "capability_id": "customer_targeting", "depends_on": ["x"]},
            ],
        ]
        for steps in cases:
            with self.subTest(steps=steps):
                planner, model = await self.planner([{"steps": steps}])
                with self.assertRaises(PlannerError) as caught:
                    await planner.plan(goal=goal(), capability_catalog=CATALOG)
                self.assertEqual(caught.exception.code, "PLAN_INVALID")
                self.assertEqual(len(model.requests), 1)

    async def test_valid_json_protocol_errors_are_not_repaired(self):
        cases = [
            {"steps": []},
            {"steps": "x"},
            {"steps": [{"step_id": "x", "capability_id": "directional_insight"}]},
            {"steps": [{"step_id": "x", "capability_id": "directional_insight", "depends_on": []}], "plan_id": "model"},
            {"steps": [], "unable_to_plan": True},
            {"unable_to_plan": False},
        ]
        for item in cases:
            with self.subTest(item=item):
                planner, model = await self.planner([item])
                with self.assertRaises(PlannerError) as caught:
                    await planner.plan(goal=goal(), capability_catalog=CATALOG)
                self.assertEqual(caught.exception.code, "PLANNER_PROTOCOL_INVALID")
                self.assertEqual(len(model.requests), 1)

    async def test_only_json_syntax_error_gets_one_repair(self):
        valid = {"steps": [{"step_id": "x", "capability_id": "directional_insight", "depends_on": []}]}
        planner, model = await self.planner(['{"steps":', valid])
        result = await planner.plan(goal=goal(), capability_catalog=CATALOG)
        self.assertEqual(result.steps[0].step_id, "x")
        self.assertEqual(len(model.requests), 2)

        planner, model = await self.planner(['{"steps":', '{"still":'])
        with self.assertRaises(PlannerError) as caught:
            await planner.plan(goal=goal(), capability_catalog=CATALOG)
        self.assertEqual(caught.exception.code, "PLANNER_PROTOCOL_INVALID")
        self.assertEqual(len(model.requests), 2)

    async def test_unable_to_plan_and_empty_catalog(self):
        planner, model = await self.planner([{"unable_to_plan": True}])
        with self.assertRaises(PlanningUnavailableError):
            await planner.plan(goal=goal(), capability_catalog=CATALOG)
        self.assertEqual(len(model.requests), 1)

        empty_model = FakeChatModel()
        empty_planner = Planner(model=empty_model, model_name="fake")
        with self.assertRaises(PlanningUnavailableError):
            await empty_planner.plan(goal=goal(), capability_catalog={})
        self.assertEqual(empty_model.requests, [])

    async def test_invalid_context_is_rejected_before_model(self):
        cases = [
            {"opportunities": ["x"]},
            {"opportunity_refs": "x"},
            {"opportunity_refs": [{}]},
        ]
        for context in cases:
            with self.subTest(context=context):
                model = FakeChatModel()
                planner = Planner(model=model, model_name="fake")
                with self.assertRaises(PlannerError) as caught:
                    await planner.plan(goal=goal(), context=context, capability_catalog=CATALOG)
                self.assertEqual(caught.exception.code, "PLANNING_CONTEXT_INVALID")
                self.assertEqual(model.requests, [])

    async def test_model_exception_is_safe(self):
        class FailingModel:
            async def complete(self, request):
                raise RuntimeError("secret sdk response")

        planner = Planner(model=FailingModel(), model_name="fake")
        with self.assertRaises(PlannerError) as caught:
            await planner.plan(goal=goal(), capability_catalog=CATALOG)
        self.assertEqual(caught.exception.code, "PLANNER_MODEL_FAILED")
        self.assertNotIn("secret", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
