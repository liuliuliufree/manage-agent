import unittest

from src.application import ExecutionContext
from src.domain import (
    CapabilityResult,
    CapabilityStatus,
    Goal,
    GoalRef,
    Plan,
    PlanStatus,
    PlanStep,
)


def goal_and_plan() -> tuple[Goal, Plan]:
    goal = Goal(
        goal_id="goal_001",
        version=1,
        original_request="帮我看看有什么经营机会。",
        goal_type="opportunity_discovery",
    )
    plan = Plan(
        plan_id="plan_001",
        version=1,
        goal_ref=GoalRef(goal_id=goal.goal_id, version=goal.version),
        status=PlanStatus.ACTIVE,
        steps=(
            PlanStep(
                step_id="inspect_opportunities",
                capability_id="directional_insight",
            ),
        ),
    )
    return goal, plan


def capability_result(status: CapabilityStatus) -> CapabilityResult:
    return CapabilityResult(
        request_id="request_001",
        capability_id="directional_insight",
        status=status,
    )


class ExecutionContextTests(unittest.TestCase):
    def test_starts_with_independent_empty_runtime_state(self) -> None:
        goal, plan = goal_and_plan()
        first = ExecutionContext(goal=goal, current_plan=plan)
        second = ExecutionContext(goal=goal, current_plan=plan)

        first.known_context["opportunity_refs"] = ["opportunity_001"]
        first.record_result(
            "inspect_opportunities",
            capability_result(CapabilityStatus.SUCCESS),
        )

        self.assertIs(first.goal, goal)
        self.assertIs(first.current_plan, plan)
        self.assertEqual(second.known_context, {})
        self.assertEqual(second.step_results, {})

    def test_record_result_does_not_merge_known_context(self) -> None:
        goal, plan = goal_and_plan()
        context = ExecutionContext(
            goal=goal,
            current_plan=plan,
            known_context={"opportunity_refs": ["opportunity_001"]},
        )
        result = capability_result(CapabilityStatus.NO_RESULT)

        context.record_result("inspect_opportunities", result)

        self.assertIs(context.step_results["inspect_opportunities"], result)
        self.assertEqual(
            context.known_context,
            {"opportunity_refs": ["opportunity_001"]},
        )

    def test_recording_same_step_replaces_its_latest_result(self) -> None:
        goal, plan = goal_and_plan()
        context = ExecutionContext(goal=goal, current_plan=plan)
        first = capability_result(CapabilityStatus.NO_RESULT)
        second = capability_result(CapabilityStatus.SUCCESS)

        context.record_result("inspect_opportunities", first)
        context.record_result("inspect_opportunities", second)

        self.assertEqual(len(context.step_results), 1)
        self.assertIs(context.step_results["inspect_opportunities"], second)


if __name__ == "__main__":
    unittest.main()
