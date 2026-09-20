import asyncio
import json
import unittest
from datetime import datetime

from openai.types.chat import ChatCompletion

from src.application import (
    CAPABILITY_CATALOG,
    CapabilityExecutor,
    ContinuationAction,
    ExecutionContext,
    Planner,
    decide_continuation,
    execute_step,
    get_next_ready_step,
)
from src.domain import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    Goal,
    GoalRef,
    Plan,
    PlanStatus,
    PlanStep,
)
from src.model import FakeChatModel


def completion(payload: dict[str, object]) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "replan-response",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": "fake-planner",
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


def initial_context() -> ExecutionContext:
    goal = Goal(
        goal_id="goal_001",
        version=1,
        original_request="完成当前经营目标。",
        goal_type="performance_achievement",
    )
    plan = Plan(
        plan_id="plan_001",
        version=1,
        goal_ref=GoalRef(goal.goal_id, goal.version),
        status=PlanStatus.ACTIVE,
        steps=(
            PlanStep("s1", "directional_insight"),
            PlanStep("s2", "customer_targeting", depends_on=("s1",)),
            PlanStep("s3", "strategy_generation", depends_on=("s2",)),
        ),
    )
    return ExecutionContext(
        goal=goal,
        current_plan=plan,
        known_context={"opportunity_refs": ["opportunity_001"]},
    )


def result(step: PlanStep, status: CapabilityStatus) -> CapabilityResult:
    return CapabilityResult(
        request_id=f"request_{step.step_id}",
        capability_id=step.capability_id,
        status=status,
    )


def replanned_steps() -> dict[str, object]:
    return {
        "steps": [
            {
                "step_id": "s1",
                "capability_id": "directional_insight",
                "depends_on": [],
            },
            {
                "step_id": "s4",
                "capability_id": "customer_targeting",
                "depends_on": ["s1"],
            },
            {
                "step_id": "s5",
                "capability_id": "strategy_generation",
                "depends_on": ["s4"],
            },
        ]
    }


def planner_for(payload: dict[str, object]) -> tuple[Planner, FakeChatModel]:
    model = FakeChatModel(completions=(completion(payload),))
    return Planner(model=model, model_name="fake-planner"), model


class ReplanningTests(unittest.TestCase):
    def test_no_result_creates_next_plan_version(self) -> None:
        context = initial_context()
        context.record_result("s1", result(context.current_plan.steps[0], CapabilityStatus.SUCCESS))
        no_result = result(context.current_plan.steps[1], CapabilityStatus.NO_RESULT)
        context.record_result("s2", no_result)
        planner, model = planner_for(replanned_steps())

        new_plan = asyncio.run(
            planner.replan(context=context, last_result=no_result)
        )

        self.assertEqual((new_plan.plan_id, new_plan.version), ("plan_001", 2))
        self.assertEqual(new_plan.supersedes_version, 1)
        self.assertEqual([step.step_id for step in new_plan.steps], ["s1", "s4", "s5"])
        request_payload = json.loads(model.requests[0]["messages"][1]["content"])
        self.assertEqual(
            request_payload["known_context"]["opportunity_refs"],
            ["opportunity_001"],
        )
        self.assertEqual(request_payload["step_results"]["s2"]["status"], "no_result")
        self.assertEqual(request_payload["last_result"]["status"], "no_result")

    def test_retained_success_step_is_not_ready_again(self) -> None:
        context = initial_context()
        context.record_result("s1", result(context.current_plan.steps[0], CapabilityStatus.SUCCESS))
        no_result = result(context.current_plan.steps[1], CapabilityStatus.NO_RESULT)
        context.record_result("s2", no_result)
        planner, _ = planner_for(replanned_steps())

        context.current_plan = asyncio.run(
            planner.replan(context=context, last_result=no_result)
        )

        self.assertEqual(get_next_ready_step(context.current_plan, context).step_id, "s4")

    def test_same_capability_can_be_repeated_with_new_step_id(self) -> None:
        context = initial_context()
        context.record_result("s1", result(context.current_plan.steps[0], CapabilityStatus.SUCCESS))
        no_result = result(context.current_plan.steps[1], CapabilityStatus.NO_RESULT)
        context.record_result("s2", no_result)
        planner, _ = planner_for(replanned_steps())

        new_plan = asyncio.run(planner.replan(context=context, last_result=no_result))

        self.assertEqual(new_plan.steps[1].step_id, "s4")
        self.assertEqual(new_plan.steps[1].capability_id, "customer_targeting")

    def test_unknown_capability_in_replan_is_rejected(self) -> None:
        context = initial_context()
        no_result = result(context.current_plan.steps[1], CapabilityStatus.NO_RESULT)
        context.record_result("s2", no_result)
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
            asyncio.run(planner.replan(context=context, last_result=no_result))

    def test_completed_step_cannot_change_capability(self) -> None:
        context = initial_context()
        context.record_result("s1", result(context.current_plan.steps[0], CapabilityStatus.SUCCESS))
        no_result = result(context.current_plan.steps[1], CapabilityStatus.NO_RESULT)
        context.record_result("s2", no_result)
        planner, _ = planner_for(
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "capability_id": "customer_targeting",
                        "depends_on": [],
                    }
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "cannot change capability_id"):
            asyncio.run(planner.replan(context=context, last_result=no_result))

    def test_no_result_replans_and_execution_finishes(self) -> None:
        context = initial_context()
        calls: list[str] = []

        def handler(request: CapabilityRequest) -> CapabilityResult:
            calls.append(request.capability_id)
            status = (
                CapabilityStatus.NO_RESULT
                if request.capability_id == "customer_targeting" and calls.count("customer_targeting") == 1
                else CapabilityStatus.SUCCESS
            )
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                status=status,
            )

        executor = CapabilityExecutor(
            {capability_id: handler for capability_id in CAPABILITY_CATALOG}
        )
        planner, _ = planner_for(replanned_steps())

        while True:
            step = get_next_ready_step(context.current_plan, context)
            self.assertIsNotNone(step)
            last_result = execute_step(step, context, executor)
            action = decide_continuation(context.current_plan, context, last_result)
            if action is ContinuationAction.REPLAN:
                context.current_plan = asyncio.run(
                    planner.replan(context=context, last_result=last_result)
                )
                continue
            if action is ContinuationAction.CONTINUE:
                continue
            self.assertEqual(action, ContinuationAction.FINISH)
            break

        self.assertEqual(
            calls,
            [
                "directional_insight",
                "customer_targeting",
                "customer_targeting",
                "strategy_generation",
            ],
        )
        self.assertEqual(context.current_plan.version, 2)


if __name__ == "__main__":
    unittest.main()
