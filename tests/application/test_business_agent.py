import asyncio
import json
import unittest
from datetime import datetime

from openai.types.chat import ChatCompletion

from src.application import (
    CAPABILITY_CATALOG,
    BusinessAgent,
    BusinessAgentStatus,
    CapabilityExecutor,
    GoalParser,
    Planner,
    RuntimeContext,
)
from src.domain import CapabilityRequest, CapabilityResult, CapabilityStatus
from src.model import FakeChatModel


def completion(payload: dict[str, object]) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "business-agent-response",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": "fake-business-agent",
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


def agent_for(
    goal_payload: dict[str, object],
    plan_capabilities: tuple[str, ...] = (),
) -> tuple[BusinessAgent, FakeChatModel, FakeChatModel]:
    goal_model = FakeChatModel(completions=(completion(goal_payload),))
    plan_model = FakeChatModel(
        completions=(
            completion(
                {
                    "steps": [
                        {
                            "step_id": f"step_{index}_{capability_id}",
                            "capability_id": capability_id,
                            "depends_on": (
                                []
                                if index == 0
                                else [
                                    f"step_{index - 1}_{plan_capabilities[index - 1]}"
                                ]
                            ),
                        }
                        for index, capability_id in enumerate(plan_capabilities)
                    ]
                }
            ),
        )
        if plan_capabilities
        else ()
    )
    agent = BusinessAgent(
        goal_parser=GoalParser(
            model=goal_model,
            model_name="fake-goal-parser",
            goal_id_factory=lambda: "goal_demo",
        ),
        planner=Planner(
            model=plan_model,
            model_name="fake-planner",
            plan_id_factory=lambda: "plan_demo",
        ),
        capability_executor=CapabilityExecutor(
            {
                capability_id: _successful_handler
                for capability_id in CAPABILITY_CATALOG
            }
        ),
    )
    return agent, goal_model, plan_model


def _successful_handler(request: CapabilityRequest) -> CapabilityResult:
    return CapabilityResult(
        request_id=request.request_id,
        capability_id=request.capability_id,
        status=CapabilityStatus.SUCCESS,
    )


def parsed_goal(
    goal_type: str,
    **fields: object,
) -> dict[str, object]:
    return {
        "goal_type": goal_type,
        "needs_clarification": False,
        "clarification_question": None,
        **fields,
    }


class BusinessAgentBehaviourTests(unittest.TestCase):
    def run_case(
        self,
        *,
        user_request: str,
        goal_payload: dict[str, object],
        plan_capabilities: tuple[str, ...],
        existing_context: dict[str, list[str]] | None = None,
    ):
        agent, _, _ = agent_for(goal_payload, plan_capabilities)
        response = asyncio.run(
            agent.handle(
                user_request=user_request,
                runtime_context=RuntimeContext(
                    actor_ref="agent_001",
                    channel_ref="individual_insurance",
                ),
                existing_context=existing_context,
            )
        )
        self.assertEqual(response.status, BusinessAgentStatus.COMPLETED)
        self.assertIsNotNone(response.goal)
        self.assertIsNotNone(response.plan)
        return response

    def test_only_opportunity_insight_is_planned(self) -> None:
        response = self.run_case(
            user_request="最近有什么值得关注的经营机会？",
            goal_payload=parsed_goal("opportunity_discovery"),
            plan_capabilities=("directional_insight",),
        )
        self.assertEqual(
            tuple(step.capability_id for step in response.plan.steps),
            ("directional_insight",),
        )

    def test_existing_opportunity_skips_insight(self) -> None:
        response = self.run_case(
            user_request="围绕刚才这个机会找一批客户。",
            goal_payload=parsed_goal("customer_targeting"),
            plan_capabilities=("customer_targeting",),
            existing_context={"opportunity_refs": ["opportunity_001"]},
        )
        self.assertEqual(response.plan.steps[0].capability_id, "customer_targeting")

    def test_existing_customer_goes_directly_to_strategy(self) -> None:
        response = self.run_case(
            user_request="王女士下一步怎么经营？",
            goal_payload=parsed_goal(
                "strategy_advice",
                audience_scope={
                    "scope_type": "specific_customer",
                    "scope_reference": "王女士",
                    "raw_expression": "王女士",
                },
            ),
            plan_capabilities=("strategy_generation",),
            existing_context={"customer_refs": ["customer_wang"]},
        )
        self.assertEqual(response.plan.steps[0].capability_id, "strategy_generation")

    def test_tracking_request_goes_directly_to_tracking(self) -> None:
        response = self.run_case(
            user_request="看看上周经营任务进展怎么样。",
            goal_payload=parsed_goal(
                "task_tracking",
                time_horizon={"raw_expression": "上周"},
            ),
            plan_capabilities=("tracking_iteration",),
            existing_context={"task_refs": ["task_001"]},
        )
        self.assertEqual(response.plan.steps[0].capability_id, "tracking_iteration")

    def test_complex_performance_goal_uses_relevant_partial_plan(self) -> None:
        response = self.run_case(
            user_request="开门红阶段完成500W NBEV，主推产品A和产品B。",
            goal_payload=parsed_goal(
                "performance_achievement",
                metric={"code": "NBEV", "display_name": "新业务价值"},
                target={
                    "target_type": "numeric",
                    "value": 500,
                    "unit": "万元",
                    "direction": "at_least",
                },
                time_horizon={"raw_expression": "开门红阶段"},
                product_mentions=["产品A", "产品B"],
            ),
            plan_capabilities=(
                "directional_insight",
                "customer_targeting",
                "strategy_generation",
            ),
        )
        capabilities = tuple(step.capability_id for step in response.plan.steps)
        self.assertLess(len(capabilities), 5)
        self.assertNotIn("tracking_iteration", capabilities)

    def test_ambiguous_metric_stops_before_planning(self) -> None:
        agent, _, plan_model = agent_for(
            {
                "goal_type": "performance_achievement",
                "metric": None,
                "target": {
                    "target_type": "numeric",
                    "value": 500,
                    "unit": "万元",
                    "direction": "at_least",
                },
                "needs_clarification": True,
                "clarification_question": "这里的500W具体指NBEV、保费还是其他指标？",
            }
        )
        response = asyncio.run(agent.handle(user_request="这个月业绩做到500W。"))
        self.assertEqual(
            response.status,
            BusinessAgentStatus.CLARIFICATION_REQUIRED,
        )
        self.assertIn("500W", response.question)
        self.assertEqual(len(plan_model.requests), 0)

    def test_non_demo_product_requires_no_code_change(self) -> None:
        response = self.run_case(
            user_request="最近主推Product X，帮我看看有什么经营机会。",
            goal_payload=parsed_goal(
                "opportunity_discovery",
                product_mentions=["Product X"],
            ),
            plan_capabilities=("directional_insight",),
        )
        self.assertEqual(
            response.goal.product_or_need_context.products,
            ("Product X",),
        )

    def test_non_opening_campaign_goal_is_supported(self) -> None:
        response = self.run_case(
            user_request="最近一个月想重点提升老客户二次经营。",
            goal_payload=parsed_goal(
                "customer_reoperation",
                time_horizon={"raw_expression": "最近一个月"},
                audience_scope={
                    "scope_type": "customer_segment",
                    "scope_reference": "老客户",
                    "raw_expression": "老客户",
                },
                need_mentions=["二次经营"],
            ),
            plan_capabilities=("directional_insight", "customer_targeting"),
        )
        self.assertEqual(response.goal.goal_type, "customer_reoperation")
        self.assertEqual(len(response.plan.steps), 2)


class BusinessAgentResponseTests(unittest.TestCase):
    def test_planning_failure_returns_failed_response(self) -> None:
        agent, _, _ = agent_for(
            parsed_goal("opportunity_discovery"),
            ("invented_capability",),
        )

        response = asyncio.run(
            agent.handle(user_request="帮我看看有什么经营机会。")
        )

        self.assertEqual(response.status, BusinessAgentStatus.FAILED)
        self.assertIsNone(response.goal)
        self.assertIsNone(response.plan)
        self.assertIn("unknown capability", response.error)


if __name__ == "__main__":
    unittest.main()
