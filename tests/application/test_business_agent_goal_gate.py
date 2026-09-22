import json
import unittest

from openai.types.chat import ChatCompletion

from src.application import (
    BusinessAgent,
    BusinessAgentStatus,
    CapabilityExecutor,
    CapabilityIO,
    GoalParser,
    Planner,
    RuntimeContext,
)
from src.domain import CapabilityResult, CapabilityStatus
from src.model import FakeChatModel


def completion(payload):
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-gate",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                }
            ],
            "created": 0,
            "model": "fake",
            "object": "chat.completion",
        }
    )


def parser_payload(metric_text="NBEV"):
    return {
        "goal_type": "performance_achievement",
        "metric_text": metric_text,
        "target_text": "500W",
        "time_text": None,
        "products": [],
        "needs": [],
        "audience_text": None,
        "constraints": [],
    }


class BusinessAgentGoalGateTests(unittest.IsolatedAsyncioTestCase):
    def make_agent(self, parser_model, planner_model, handler):
        return BusinessAgent(
            goal_parser=GoalParser(
                model=parser_model,
                model_name="fake",
                goal_id_factory=lambda: "goal-1",
            ),
            planner=Planner(
                model=planner_model,
                model_name="fake",
                plan_id_factory=lambda: "plan-1",
            ),
            capability_executor=CapabilityExecutor({"insight": handler}),
            capability_io={"insight": CapabilityIO()},
            capability_catalog={"insight": {"description": "synthetic"}},
        )

    async def test_real_parser_result_reaches_planner_and_one_plan_executes(self):
        parser_model = FakeChatModel(completions=[completion(parser_payload())])
        planner_model = FakeChatModel(
            completions=[
                completion(
                    {
                        "steps": [
                            {
                                "step_id": "inspect",
                                "capability_id": "insight",
                                "depends_on": [],
                            }
                        ]
                    }
                )
            ]
        )
        seen_goal_refs = []

        def handler(request):
            seen_goal_refs.append(request.goal_ref)
            return CapabilityResult(
                request.request_id,
                request.capability_id,
                CapabilityStatus.SUCCESS,
            )

        response = await self.make_agent(parser_model, planner_model, handler).handle(
            user_request="目标500W NBEV",
            runtime_context=RuntimeContext("agent-1", "individual", "demo_runtime"),
        )
        self.assertIs(response.status, BusinessAgentStatus.COMPLETED)
        self.assertEqual(response.plan.version, 1)
        self.assertEqual(seen_goal_refs[0].goal_id, "goal-1")
        self.assertEqual(len(parser_model.requests), 1)
        self.assertEqual(len(planner_model.requests), 1)

    async def test_blocking_partial_goal_never_calls_planner_or_handler(self):
        parser_model = FakeChatModel(completions=[completion(parser_payload("业绩"))])
        planner_model = FakeChatModel()
        handler_calls = []

        def handler(request):
            handler_calls.append(request)
            raise AssertionError("must not execute")

        response = await self.make_agent(parser_model, planner_model, handler).handle(
            user_request="目标500W业绩",
            runtime_context=RuntimeContext("agent-1", "individual", "demo_runtime"),
        )
        self.assertIs(response.status, BusinessAgentStatus.CLARIFICATION_REQUIRED)
        self.assertEqual(planner_model.requests, [])
        self.assertEqual(handler_calls, [])


if __name__ == "__main__":
    unittest.main()
