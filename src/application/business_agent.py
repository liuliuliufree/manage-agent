"""Lightweight application orchestrator from request through plan execution."""

from dataclasses import dataclass
from enum import StrEnum

from src.domain import CapabilityResult, Goal, Plan

from .capability.capability_catalog import CAPABILITY_CATALOG
from .capability.capability_executor import CapabilityExecutor
from .capability.continuation import ContinuationAction, decide_continuation
from .capability.execution_context import ExecutionContext
from .goal_parser import GoalParser, GoalParseStatus, RuntimeContext
from .planner.planner import CapabilityCatalog, ExistingContext, Planner
from .planner.plan_validation import validate_plan
from .capability.step_execution import execute_step
from .capability.step_resolution import get_next_ready_step


class BusinessAgentStatus(StrEnum):
    COMPLETED = "COMPLETED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class BusinessAgentResponse:
    """Small response shared by parsing, planning, and execution outcomes."""

    status: BusinessAgentStatus
    goal: Goal | None = None
    plan: Plan | None = None
    execution_context: ExecutionContext | None = None
    last_result: CapabilityResult | None = None
    question: str | None = None
    message: str | None = None
    error: str | None = None


class BusinessAgent:
    """Connect Goal parsing, planning, and the minimal capability loop."""

    def __init__(
        self,
        *,
        goal_parser: GoalParser,
        planner: Planner,
        capability_executor: CapabilityExecutor,
        capability_catalog: CapabilityCatalog = CAPABILITY_CATALOG,
    ) -> None:
        if not capability_catalog:
            raise ValueError("Capability catalog must not be empty")
        self._goal_parser = goal_parser
        self._planner = planner
        self._capability_executor = capability_executor
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
            if parse_result.status is GoalParseStatus.TECHNICAL_FAILURE:
                return BusinessAgentResponse(
                    status=BusinessAgentStatus.FAILED,
                    goal=parse_result.goal,
                    error=parse_result.error or "Goal parser failed",
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
            context = ExecutionContext(
                goal=goal,
                current_plan=plan,
                known_context=dict(existing_context or {}),
            )
            return await self._execute_plan(context)
        except Exception as exc:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.FAILED,
                error=str(exc) or type(exc).__name__,
            )

    async def _execute_plan(
        self,
        context: ExecutionContext,
    ) -> BusinessAgentResponse:
        replan_count = 0

        while True:
            step = get_next_ready_step(context.current_plan, context)
            if step is None:
                return self._stopped_response(
                    context,
                    message="Plan has no executable step",
                )

            result = execute_step(step, context, self._capability_executor)
            action = decide_continuation(
                context.current_plan,
                context,
                result,
            )

            if action is ContinuationAction.CONTINUE:
                continue
            if action is ContinuationAction.FINISH:
                return BusinessAgentResponse(
                    status=BusinessAgentStatus.COMPLETED,
                    goal=context.goal,
                    plan=context.current_plan,
                    execution_context=context,
                    last_result=result,
                )
            if action is ContinuationAction.ASK_USER:
                question = "; ".join(
                    item.reason for item in result.missing_information
                )
                return BusinessAgentResponse(
                    status=BusinessAgentStatus.CLARIFICATION_REQUIRED,
                    goal=context.goal,
                    plan=context.current_plan,
                    execution_context=context,
                    last_result=result,
                    question=question,
                )
            if action is ContinuationAction.STOP:
                return self._stopped_response(context, last_result=result)

            if replan_count >= 1:
                return self._stopped_response(
                    context,
                    last_result=result,
                    message="Maximum replan count reached",
                )

            context.current_plan = await self._planner.replan(
                context=context,
                last_result=result,
                capability_catalog=self._capability_catalog,
            )
            replan_count += 1

    @staticmethod
    def _stopped_response(
        context: ExecutionContext,
        *,
        last_result: CapabilityResult | None = None,
        message: str | None = None,
    ) -> BusinessAgentResponse:
        return BusinessAgentResponse(
            status=BusinessAgentStatus.STOPPED,
            goal=context.goal,
            plan=context.current_plan,
            execution_context=context,
            last_result=last_result,
            message=message,
        )
