import unittest

from src.application import (
    ContinuationAction,
    ExecutionContext,
    decide_continuation,
    is_plan_finished,
)
from src.domain import (
    CapabilityError,
    CapabilityResult,
    CapabilityStatus,
    ErrorCategory,
    Goal,
    GoalRef,
    MissingInformation,
    Plan,
    PlanStatus,
    PlanStep,
)


def three_step_context() -> tuple[Plan, ExecutionContext]:
    goal = Goal(
        goal_id="goal_001",
        version=1,
        original_request="完成一个三步经营目标。",
        goal_type="customer_operation",
    )
    plan = Plan(
        plan_id="plan_001",
        version=1,
        goal_ref=GoalRef(goal_id=goal.goal_id, version=goal.version),
        status=PlanStatus.ACTIVE,
        steps=(
            PlanStep(step_id="s1", capability_id="directional_insight"),
            PlanStep(
                step_id="s2",
                capability_id="customer_targeting",
                depends_on=("s1",),
            ),
            PlanStep(
                step_id="s3",
                capability_id="strategy_generation",
                depends_on=("s2",),
            ),
        ),
    )
    return plan, ExecutionContext(goal=goal, current_plan=plan)


def result_for(step: PlanStep, status: CapabilityStatus) -> CapabilityResult:
    kwargs: dict[str, object] = {}
    if status is CapabilityStatus.PARTIAL_SUCCESS:
        kwargs["limitations"] = ("Partial test result",)
    elif status is CapabilityStatus.NEED_INFORMATION:
        kwargs["missing_information"] = (
            MissingInformation(
                field="region",
                reason="经营区域缺失",
                impact="无法确定圈客范围",
            ),
        )
    elif status is CapabilityStatus.BLOCKED:
        kwargs["rule_result_refs"] = ("rule_result_001",)
    elif status is CapabilityStatus.FAILED:
        kwargs["errors"] = (
            CapabilityError(
                category=ErrorCategory.INTERNAL,
                code="test_failure",
                message="Test failure",
            ),
        )
    return CapabilityResult(
        request_id=f"request_{step.step_id}",
        capability_id=step.capability_id,
        status=status,
        **kwargs,
    )


class ContinuationTests(unittest.TestCase):
    def test_success_continues_when_a_later_step_is_ready(self) -> None:
        plan, context = three_step_context()
        result = result_for(plan.steps[0], CapabilityStatus.SUCCESS)
        context.record_result("s1", result)

        self.assertEqual(
            decide_continuation(plan, context, result),
            ContinuationAction.CONTINUE,
        )

    def test_success_finishes_when_all_steps_are_complete(self) -> None:
        plan, context = three_step_context()
        for step in plan.steps:
            context.record_result(
                step.step_id,
                result_for(step, CapabilityStatus.SUCCESS),
            )

        last_result = context.step_results["s3"]
        self.assertTrue(is_plan_finished(plan, context))
        self.assertEqual(
            decide_continuation(plan, context, last_result),
            ContinuationAction.FINISH,
        )

    def test_partial_success_continues_when_a_later_step_is_ready(self) -> None:
        plan, context = three_step_context()
        result = result_for(plan.steps[0], CapabilityStatus.PARTIAL_SUCCESS)
        context.record_result("s1", result)

        self.assertEqual(
            decide_continuation(plan, context, result),
            ContinuationAction.CONTINUE,
        )

    def test_no_result_requests_replan(self) -> None:
        self._assert_direct_mapping(
            CapabilityStatus.NO_RESULT,
            ContinuationAction.REPLAN,
        )

    def test_need_information_asks_user(self) -> None:
        self._assert_direct_mapping(
            CapabilityStatus.NEED_INFORMATION,
            ContinuationAction.ASK_USER,
        )

    def test_blocked_stops(self) -> None:
        self._assert_direct_mapping(
            CapabilityStatus.BLOCKED,
            ContinuationAction.STOP,
        )

    def test_failed_stops(self) -> None:
        self._assert_direct_mapping(
            CapabilityStatus.FAILED,
            ContinuationAction.STOP,
        )

    def test_success_stops_when_plan_is_incomplete_without_ready_step(self) -> None:
        plan, context = three_step_context()
        success = result_for(plan.steps[0], CapabilityStatus.SUCCESS)
        blocked = result_for(plan.steps[1], CapabilityStatus.BLOCKED)
        context.record_result("s1", success)
        context.record_result("s2", blocked)

        self.assertFalse(is_plan_finished(plan, context))
        self.assertEqual(
            decide_continuation(plan, context, success),
            ContinuationAction.STOP,
        )

    def _assert_direct_mapping(
        self,
        status: CapabilityStatus,
        expected: ContinuationAction,
    ) -> None:
        plan, context = three_step_context()
        result = result_for(plan.steps[0], status)
        context.record_result("s1", result)

        self.assertEqual(decide_continuation(plan, context, result), expected)


if __name__ == "__main__":
    unittest.main()
