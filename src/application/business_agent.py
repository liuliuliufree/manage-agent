"""Lightweight application orchestrator for the M2-Lite request path."""

from dataclasses import dataclass
from enum import StrEnum

from src.domain import Goal, Plan

from .capability_catalog import CAPABILITY_CATALOG
from .goal_parser import GoalParser, RuntimeContext
from .planner import CapabilityCatalog, ExistingContext, Planner
from .plan_validation import validate_plan


class BusinessAgentStatus(StrEnum):
    PLAN_READY = "PLAN_READY"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class BusinessAgentResponse:
    """One of the three deliberately small M2-Lite response shapes."""

    status: BusinessAgentStatus
    goal: Goal | None = None
    plan: Plan | None = None
    question: str | None = None
    error: str | None = None


class BusinessAgent:
    """Connect Goal parsing and planning without becoming another Agent Loop."""

    def __init__(
        self,
        *,
        goal_parser: GoalParser,
        planner: Planner,
        capability_catalog: CapabilityCatalog = CAPABILITY_CATALOG,
    ) -> None:
        if not capability_catalog:
            raise ValueError("Capability catalog must not be empty")
        self._goal_parser = goal_parser
        self._planner = planner
        self._capability_catalog = capability_catalog

    async def handle(
        self,
        *,
        user_request: str,
        runtime_context: RuntimeContext | None = None,
        existing_goal: Goal | None = None,
        existing_context: ExistingContext | None = None,
    ) -> BusinessAgentResponse:
        try:
            parse_result = await self._goal_parser.parse(
                user_request=user_request,
                runtime_context=runtime_context,
                existing_goal=existing_goal,
            )
            if parse_result.need_clarification:
                return BusinessAgentResponse(
                    status=BusinessAgentStatus.CLARIFICATION_REQUIRED,
                    goal=parse_result.goal,
                    question=parse_result.clarification_question,
                )

            goal = parse_result.goal
            if goal is None:
                raise ValueError("Goal parser returned no Goal")

            plan = await self._planner.plan(
                goal=goal,
                context=existing_context,
                capability_catalog=self._capability_catalog,
            )
            validate_plan(plan, self._capability_catalog)
            return BusinessAgentResponse(
                status=BusinessAgentStatus.PLAN_READY,
                goal=goal,
                plan=plan,
            )
        except Exception as exc:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.FAILED,
                error=str(exc) or type(exc).__name__,
            )
