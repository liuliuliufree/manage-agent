import unittest

from src.application import (
    CapabilityExecutor,
    ExecutionContext,
    build_capability_request,
    execute_step,
)
from src.domain import (
    CapabilityOutput,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ChannelAndActor,
    Goal,
    GoalRef,
    Plan,
    PlanStatus,
    PlanStep,
)


def execution_context() -> tuple[PlanStep, ExecutionContext]:
    goal = Goal(
        goal_id="goal_001",
        version=2,
        original_request="帮我看看现有客户里有什么经营机会。",
        goal_type="opportunity_discovery",
        channel_and_actor=ChannelAndActor(
            actor_id="agent_001",
            channel_id="individual_insurance",
            context_source="runtime_context",
        ),
    )
    step = PlanStep(
        step_id="inspect_opportunities",
        capability_id="directional_insight",
    )
    plan = Plan(
        plan_id="plan_001",
        version=3,
        goal_ref=GoalRef(goal_id=goal.goal_id, version=goal.version),
        status=PlanStatus.ACTIVE,
        steps=(step,),
    )
    context = ExecutionContext(
        goal=goal,
        current_plan=plan,
        known_context={"customer_refs": ["customer_001"]},
    )
    return step, context


class StepExecutionTests(unittest.TestCase):
    def test_build_request_maps_step_and_current_context(self) -> None:
        step, context = execution_context()

        request = build_capability_request(step, context)

        self.assertTrue(request.request_id.startswith("capability_request_"))
        self.assertEqual(request.capability_id, step.capability_id)
        self.assertEqual(request.goal_ref, GoalRef(goal_id="goal_001", version=2))
        self.assertEqual(request.plan_ref.plan_id, "plan_001")
        self.assertEqual(request.plan_ref.version, 3)
        self.assertEqual(request.actor_context.actor_id, "agent_001")
        self.assertEqual(request.actor_context.channel_id, "individual_insurance")
        self.assertEqual(request.actor_context.trusted_source, "runtime_context")
        self.assertEqual(request.input_refs, ("customer:customer_001",))

    def test_execute_step_dispatches_request_and_records_success(self) -> None:
        step, context = execution_context()
        received_requests: list[CapabilityRequest] = []

        def handler(request: CapabilityRequest) -> CapabilityResult:
            received_requests.append(request)
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                status=CapabilityStatus.SUCCESS,
                outputs=(
                    CapabilityOutput(
                        output_id="output_001",
                        output_type="opportunity_refs",
                        summary="Found one opportunity",
                    ),
                ),
            )

        result = execute_step(
            step,
            context,
            CapabilityExecutor({step.capability_id: handler}),
        )

        self.assertEqual(len(received_requests), 1)
        self.assertEqual(received_requests[0].capability_id, step.capability_id)
        self.assertIs(context.step_results[step.step_id], result)
        self.assertEqual(result.status, CapabilityStatus.SUCCESS)

    def test_execute_step_records_executor_failure(self) -> None:
        step, context = execution_context()

        result = execute_step(step, context, CapabilityExecutor({}))

        self.assertEqual(result.status, CapabilityStatus.FAILED)
        self.assertIs(context.step_results[step.step_id], result)


if __name__ == "__main__":
    unittest.main()
