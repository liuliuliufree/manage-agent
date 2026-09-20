import unittest

from src.application import CapabilityExecutor
from src.domain import (
    ActorContext,
    CapabilityContext,
    CapabilityOutput,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ErrorCategory,
    GoalRef,
    PlanRef,
)


def capability_request(capability_id: str = "directional_insight") -> CapabilityRequest:
    return CapabilityRequest(
        request_id="request_001",
        capability_id=capability_id,
        goal_ref=GoalRef(goal_id="goal_001", version=1),
        plan_ref=PlanRef(plan_id="plan_001", version=1),
        context=CapabilityContext(
            actor=ActorContext(
                actor_id="agent_001",
                channel_id="individual_insurance",
                trusted_source="runtime_context",
            )
        ),
    )


class CapabilityExecutorTests(unittest.TestCase):
    def test_registered_handler_receives_request_and_returns_result(self) -> None:
        request = capability_request()
        received_requests: list[CapabilityRequest] = []
        expected = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status=CapabilityStatus.SUCCESS,
            outputs=(
                CapabilityOutput(
                    output_id="output_001",
                    output_type="opportunity_refs",
                    summary="Found one opportunity",
                    payload={"refs": ["opportunity_001"]},
                ),
            ),
        )

        def handler(actual_request: CapabilityRequest) -> CapabilityResult:
            received_requests.append(actual_request)
            return expected

        result = CapabilityExecutor({request.capability_id: handler}).execute(request)

        self.assertIs(result, expected)
        self.assertEqual(received_requests, [request])

    def test_missing_handler_returns_failed_result(self) -> None:
        request = capability_request("customer_targeting")

        result = CapabilityExecutor({}).execute(request)

        self.assertEqual(result.request_id, request.request_id)
        self.assertEqual(result.capability_id, request.capability_id)
        self.assertEqual(result.status, CapabilityStatus.FAILED)
        self.assertEqual(result.errors[0].category, ErrorCategory.DEPENDENCY)
        self.assertEqual(result.errors[0].code, "capability_handler_not_found")

    def test_handler_exception_returns_failed_result(self) -> None:
        request = capability_request()

        def failing_handler(_: CapabilityRequest) -> CapabilityResult:
            raise RuntimeError("upstream capability failed")

        result = CapabilityExecutor(
            {request.capability_id: failing_handler}
        ).execute(request)

        self.assertEqual(result.request_id, request.request_id)
        self.assertEqual(result.capability_id, request.capability_id)
        self.assertEqual(result.status, CapabilityStatus.FAILED)
        self.assertEqual(result.errors[0].category, ErrorCategory.INTERNAL)
        self.assertEqual(result.errors[0].code, "capability_handler_failed")
        self.assertEqual(result.errors[0].message, "upstream capability failed")


if __name__ == "__main__":
    unittest.main()
