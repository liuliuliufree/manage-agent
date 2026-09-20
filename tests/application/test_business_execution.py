import asyncio
import json
import unittest
from collections.abc import Callable
from datetime import datetime

from openai.types.chat import ChatCompletion

from src.application import (
    CAPABILITY_CATALOG,
    BusinessAgent,
    BusinessAgentStatus,
    CapabilityExecutor,
    GoalParser,
    Planner,
)
from src.domain import (
    CapabilityError,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ErrorCategory,
    MissingInformation,
)
from src.model import FakeChatModel


def completion(payload: dict[str, object]) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "business-execution-response",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": "fake-model",
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


def plan_payload(*steps: tuple[str, str, tuple[str, ...]]) -> dict[str, object]:
    return {
        "steps": [
            {
                "step_id": step_id,
                "capability_id": capability_id,
                "depends_on": list(depends_on),
            }
            for step_id, capability_id, depends_on in steps
        ]
    }


def build_agent(
    *,
    plan_payloads: tuple[dict[str, object], ...],
    handler: Callable[[CapabilityRequest], CapabilityResult],
) -> tuple[BusinessAgent, FakeChatModel]:
    goal_model = FakeChatModel(
        completions=(
            completion(
                {
                    "goal_type": "opportunity_discovery",
                    "needs_clarification": False,
                    "clarification_question": None,
                }
            ),
        )
    )
    planner_model = FakeChatModel(
        completions=tuple(completion(payload) for payload in plan_payloads)
    )
    agent = BusinessAgent(
        goal_parser=GoalParser(
            model=goal_model,
            model_name="fake-goal-parser",
            goal_id_factory=lambda: "goal_execution",
        ),
        planner=Planner(
            model=planner_model,
            model_name="fake-planner",
            plan_id_factory=lambda: "plan_execution",
        ),
        capability_executor=CapabilityExecutor(
            {capability_id: handler for capability_id in CAPABILITY_CATALOG}
        ),
    )
    return agent, planner_model


def result(
    request: CapabilityRequest,
    status: CapabilityStatus,
) -> CapabilityResult:
    fields: dict[str, object] = {}
    if status is CapabilityStatus.NEED_INFORMATION:
        fields["missing_information"] = (
            MissingInformation(
                field="customer_scope",
                reason="需要客户范围",
                impact="无法圈选客户",
                required_before_execution=True,
            ),
        )
    elif status is CapabilityStatus.BLOCKED:
        fields["rule_result_refs"] = ("rule_result_001",)
    elif status is CapabilityStatus.FAILED:
        fields["errors"] = (
            CapabilityError(
                category=ErrorCategory.INTERNAL,
                code="fake_failure",
                message="fake capability failed",
            ),
        )
    return CapabilityResult(
        request_id=request.request_id,
        capability_id=request.capability_id,
        status=status,
        **fields,
    )


class BusinessExecutionTests(unittest.TestCase):
    def test_normal_plan_executes_each_step_once_without_replan(self) -> None:
        calls: list[str] = []

        def handler(request: CapabilityRequest) -> CapabilityResult:
            calls.append(request.capability_id)
            return result(request, CapabilityStatus.SUCCESS)

        agent, planner_model = build_agent(
            plan_payloads=(
                plan_payload(
                    ("s1", "directional_insight", ()),
                    ("s2", "customer_targeting", ("s1",)),
                    ("s3", "strategy_generation", ("s2",)),
                ),
            ),
            handler=handler,
        )

        response = asyncio.run(agent.handle(user_request="找机会、客户并形成策略。"))

        self.assertEqual(response.status, BusinessAgentStatus.COMPLETED)
        self.assertEqual(
            calls,
            ["directional_insight", "customer_targeting", "strategy_generation"],
        )
        self.assertEqual(len(planner_model.requests), 1)

    def test_no_result_replans_once_and_retains_successful_step(self) -> None:
        calls: list[str] = []

        def handler(request: CapabilityRequest) -> CapabilityResult:
            calls.append(request.capability_id)
            status = (
                CapabilityStatus.NO_RESULT
                if request.capability_id == "customer_targeting"
                and calls.count("customer_targeting") == 1
                else CapabilityStatus.SUCCESS
            )
            return result(request, status)

        agent, planner_model = build_agent(
            plan_payloads=(
                plan_payload(
                    ("s1", "directional_insight", ()),
                    ("s2", "customer_targeting", ("s1",)),
                    ("s3", "strategy_generation", ("s2",)),
                ),
                plan_payload(
                    ("s1", "directional_insight", ()),
                    ("s4", "customer_targeting", ("s1",)),
                    ("s5", "strategy_generation", ("s4",)),
                ),
            ),
            handler=handler,
        )

        response = asyncio.run(agent.handle(user_request="找机会、客户并形成策略。"))

        self.assertEqual(response.status, BusinessAgentStatus.COMPLETED)
        self.assertEqual(response.plan.version, 2)
        self.assertEqual(len(planner_model.requests), 2)
        self.assertEqual(calls.count("directional_insight"), 1)
        self.assertEqual(calls.count("customer_targeting"), 2)
        self.assertEqual(calls.count("strategy_generation"), 1)
        self.assertEqual(
            set(response.execution_context.step_results),
            {"s1", "s2", "s4", "s5"},
        )

    def test_need_information_asks_user_without_replan(self) -> None:
        agent, planner_model = build_agent(
            plan_payloads=(
                plan_payload(("s1", "customer_targeting", ())),
            ),
            handler=lambda request: result(
                request,
                CapabilityStatus.NEED_INFORMATION,
            ),
        )

        response = asyncio.run(agent.handle(user_request="帮我找客户。"))

        self.assertEqual(
            response.status,
            BusinessAgentStatus.CLARIFICATION_REQUIRED,
        )
        self.assertEqual(response.question, "需要客户范围")
        self.assertEqual(len(planner_model.requests), 1)

    def test_blocked_stops_without_replan(self) -> None:
        agent, planner_model = build_agent(
            plan_payloads=(
                plan_payload(("s1", "validation_distribution", ())),
            ),
            handler=lambda request: result(request, CapabilityStatus.BLOCKED),
        )

        response = asyncio.run(agent.handle(user_request="校验并分发任务。"))

        self.assertEqual(response.status, BusinessAgentStatus.STOPPED)
        self.assertEqual(response.last_result.status, CapabilityStatus.BLOCKED)
        self.assertEqual(len(planner_model.requests), 1)

    def test_failed_stops_without_retry_or_replan(self) -> None:
        calls = 0

        def handler(request: CapabilityRequest) -> CapabilityResult:
            nonlocal calls
            calls += 1
            return result(request, CapabilityStatus.FAILED)

        agent, planner_model = build_agent(
            plan_payloads=(
                plan_payload(("s1", "customer_targeting", ())),
            ),
            handler=handler,
        )

        response = asyncio.run(agent.handle(user_request="帮我找客户。"))

        self.assertEqual(response.status, BusinessAgentStatus.STOPPED)
        self.assertEqual(response.last_result.status, CapabilityStatus.FAILED)
        self.assertEqual(calls, 1)
        self.assertEqual(len(planner_model.requests), 1)


if __name__ == "__main__":
    unittest.main()
