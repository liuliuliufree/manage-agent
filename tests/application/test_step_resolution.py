import unittest

from src.application import (
    CapabilityExecutor,
    ExecutionContext,
    execute_step,
    get_next_ready_step,
    is_step_ready,
)
from src.domain import (
    CapabilityError,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ErrorCategory,
    Goal,
    GoalRef,
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


def capability_result(
    step: PlanStep,
    status: CapabilityStatus,
) -> CapabilityResult:
    if status is CapabilityStatus.FAILED:
        return CapabilityResult(
            request_id=f"request_{step.step_id}",
            capability_id=step.capability_id,
            status=status,
            errors=(
                CapabilityError(
                    category=ErrorCategory.INTERNAL,
                    code="test_failure",
                    message="Test failure",
                ),
            ),
        )
    if status is CapabilityStatus.BLOCKED:
        return CapabilityResult(
            request_id=f"request_{step.step_id}",
            capability_id=step.capability_id,
            status=status,
            rule_result_refs=("rule_result_001",),
        )
    if status is CapabilityStatus.PARTIAL_SUCCESS:
        return CapabilityResult(
            request_id=f"request_{step.step_id}",
            capability_id=step.capability_id,
            status=status,
            limitations=("Partial test result",),
        )
    return CapabilityResult(
        request_id=f"request_{step.step_id}",
        capability_id=step.capability_id,
        status=status,
    )


class StepResolutionTests(unittest.TestCase):
    def test_step_without_dependencies_is_ready_until_executed(self) -> None:
        plan, context = three_step_context()
        first = plan.steps[0]

        self.assertTrue(is_step_ready(first, context))

        context.record_result(
            first.step_id,
            capability_result(first, CapabilityStatus.SUCCESS),
        )

        self.assertFalse(is_step_ready(first, context))

    def test_incomplete_dependency_keeps_step_not_ready(self) -> None:
        plan, context = three_step_context()

        self.assertFalse(is_step_ready(plan.steps[1], context))

    def test_successful_dependency_releases_next_step(self) -> None:
        for status in (
            CapabilityStatus.SUCCESS,
            CapabilityStatus.PARTIAL_SUCCESS,
        ):
            with self.subTest(status=status):
                plan, context = three_step_context()
                first, second = plan.steps[:2]
                context.record_result(
                    first.step_id,
                    capability_result(first, status),
                )

                self.assertTrue(is_step_ready(second, context))

    def test_non_successful_dependency_does_not_release_next_step(self) -> None:
        for status in (
            CapabilityStatus.NO_RESULT,
            CapabilityStatus.FAILED,
            CapabilityStatus.BLOCKED,
        ):
            with self.subTest(status=status):
                plan, context = three_step_context()
                first, second = plan.steps[:2]
                context.record_result(
                    first.step_id,
                    capability_result(first, status),
                )

                self.assertFalse(is_step_ready(second, context))
                self.assertIsNone(get_next_ready_step(plan, context))

    def test_next_ready_step_uses_plan_order(self) -> None:
        plan, context = three_step_context()
        parallel = PlanStep(step_id="parallel", capability_id="tracking_iteration")
        plan = Plan(
            plan_id=plan.plan_id,
            version=plan.version,
            goal_ref=plan.goal_ref,
            status=plan.status,
            steps=(plan.steps[0], parallel, *plan.steps[1:]),
        )

        self.assertIs(get_next_ready_step(plan, context), plan.steps[0])

        context.record_result(
            plan.steps[0].step_id,
            capability_result(plan.steps[0], CapabilityStatus.SUCCESS),
        )

        self.assertIs(get_next_ready_step(plan, context), parallel)

    def test_three_steps_execute_once_in_dependency_order(self) -> None:
        plan, context = three_step_context()
        executed_capabilities: list[str] = []

        def handler(request: CapabilityRequest) -> CapabilityResult:
            executed_capabilities.append(request.capability_id)
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                status=CapabilityStatus.SUCCESS,
            )

        executor = CapabilityExecutor(
            {step.capability_id: handler for step in plan.steps}
        )

        while (step := get_next_ready_step(plan, context)) is not None:
            execute_step(step, context, executor)

        self.assertEqual(
            executed_capabilities,
            [step.capability_id for step in plan.steps],
        )
        self.assertEqual(set(context.step_results), {"s1", "s2", "s3"})


if __name__ == "__main__":
    unittest.main()
