"""Single-Plan Demo V1 orchestration from Goal parsing through capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from src.domain import CapabilityResult, Goal, GoalRef, MissingInformation, Plan

from .capability.artifact_flow import (
    ArtifactFlowError,
    CapabilityIO,
    normalize_initial_refs,
)
from .capability.artifact_store import ArtifactStore
from .capability.capability_catalog import CAPABILITY_CATALOG
from .capability.capability_executor import CapabilityExecutor
from .capability.continuation import ContinuationAction, decide_continuation
from .capability.execution_context import ExecutionContext
from .capability.step_execution import execute_step
from .capability.step_resolution import get_next_ready_step
from .goal_parser import GoalParser, GoalParseStatus, RuntimeContext
from .planner.planner import (
    CapabilityCatalog,
    ExistingContext,
    Planner,
    PlannerError,
    PlanningUnavailableError,
)
from .planner.plan_validation import validate_plan


class BusinessAgentStatus(StrEnum):
    COMPLETED = "COMPLETED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class BusinessAgentResponse:
    status: BusinessAgentStatus
    goal: Goal | None = None
    plan: Plan | None = None
    execution_context: ExecutionContext | None = None
    last_result: CapabilityResult | None = None
    question: str | None = None
    message: str | None = None
    error: str | None = None
    missing_information: tuple[MissingInformation, ...] = ()


class BusinessAgent:
    """Execute at most one Plan; stopping outcomes never trigger a second Plan."""

    def __init__(
        self,
        *,
        goal_parser: GoalParser,
        planner: Planner,
        capability_executor: CapabilityExecutor,
        capability_io: Mapping[str, CapabilityIO],
        capability_catalog: CapabilityCatalog = CAPABILITY_CATALOG,
    ) -> None:
        self._goal_parser = goal_parser
        self._planner = planner
        self._capability_executor = capability_executor
        self._capability_io = dict(capability_io)
        self._capability_catalog = dict(capability_catalog)

    async def handle(
        self,
        *,
        user_request: str,
        runtime_context: RuntimeContext | None = None,
        existing_goal: Goal | None = None,
        existing_context: ExistingContext | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> BusinessAgentResponse:
        try:
            parse_result = await self._goal_parser.parse(
                user_request=user_request,
                runtime_context=runtime_context,
                existing_goal=existing_goal,
            )
        except Exception:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.FAILED,
                error="GOAL_PARSER_FAILED",
                message="目标解析失败。",
            )

        if parse_result.status is GoalParseStatus.TECHNICAL_FAILURE:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.FAILED,
                goal=parse_result.goal,
                error=parse_result.error,
                message="目标解析失败。",
            )
        blocking_missing = tuple(
            item
            for item in (
                parse_result.goal.missing_information
                if parse_result.goal is not None
                else parse_result.missing_information
            )
            if item.required_before_execution
        )
        if parse_result.need_clarification or blocking_missing:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.CLARIFICATION_REQUIRED,
                goal=parse_result.goal,
                question=(
                    parse_result.clarification_question
                    or "请补全后重新提交完整目标。"
                ),
                missing_information=(
                    parse_result.missing_information or blocking_missing
                ),
            )
        goal = parse_result.goal
        if parse_result.status is not GoalParseStatus.SUCCESS or goal is None:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.FAILED,
                goal=goal,
                error="GOAL_PARSE_RESULT_INVALID",
                message="目标解析结果不一致。",
            )

        executable_catalog = {
            capability_id: definition
            for capability_id, definition in self._capability_catalog.items()
            if capability_id in self._capability_executor.available_capability_ids
        }
        missing_io = sorted(set(executable_catalog) - self._capability_io.keys())
        if missing_io:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.FAILED,
                goal=goal,
                error="CAPABILITY_IO_MISSING",
                message="可执行能力缺少输入输出声明。",
            )

        store = artifact_store or ArtifactStore()
        allowed_types = frozenset(
            artifact_type
            for capability_id in executable_catalog
            for artifact_type in (
                *self._capability_io[capability_id].required_inputs,
                *self._capability_io[capability_id].optional_inputs,
                *self._capability_io[capability_id].output_types,
            )
        )
        try:
            store.bind_goal(GoalRef(goal.goal_id, goal.version))
            initial_refs = normalize_initial_refs(
                dict(existing_context or {}),
                store=store,
                allowed_types=allowed_types,
            )
        except ArtifactFlowError as exc:
            return self._artifact_error_response(exc, goal=goal)

        try:
            plan = await self._planner.plan(
                goal=goal,
                context=existing_context,
                capability_catalog=executable_catalog,
            )
            validate_plan(plan, executable_catalog)
        except PlanningUnavailableError as exc:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.STOPPED,
                goal=goal,
                message=exc.message,
            )
        except PlannerError as exc:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.FAILED,
                goal=goal,
                error=exc.code,
                message=exc.message,
            )
        except Exception:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.FAILED,
                goal=goal,
                error="PLAN_INVALID",
                message="规划结果未通过确定性校验。",
            )

        context = ExecutionContext(
            goal=goal,
            current_plan=plan,
            known_context=dict(existing_context or {}),
            artifact_store=store,
            initial_refs=initial_refs,
        )
        return self._execute_plan(context)

    def _execute_plan(self, context: ExecutionContext) -> BusinessAgentResponse:
        while True:
            step = get_next_ready_step(context.current_plan, context)
            if step is None:
                return self._stopped_response(
                    context, message="当前计划没有可执行步骤。"
                )
            io = self._capability_io.get(step.capability_id)
            if io is None:
                error = ArtifactFlowError(
                    "CAPABILITY_IO_MISSING", "当前能力缺少输入输出声明。"
                )
                return self._artifact_error_response(error, context=context)
            try:
                result = execute_step(
                    step,
                    context,
                    self._capability_executor,
                    io=io,
                )
            except ArtifactFlowError as exc:
                return self._artifact_error_response(exc, context=context)

            action = decide_continuation(context.current_plan, context, result)
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
                return BusinessAgentResponse(
                    status=BusinessAgentStatus.CLARIFICATION_REQUIRED,
                    goal=context.goal,
                    plan=context.current_plan,
                    execution_context=context,
                    last_result=result,
                    question="请补全后重新提交完整目标。",
                    missing_information=result.missing_information,
                )
            return self._stopped_response(
                context,
                last_result=result,
                message=self._stop_message(result),
            )

    @staticmethod
    def _stop_message(result: CapabilityResult) -> str:
        messages = {
            "no_result": "当前能力未产生结果，本次运行已停止。",
            "partial_success": "当前能力仅部分完成，本次运行已停止。",
            "blocked": "确定性规则阻断了执行，本次运行已停止。",
            "failed": "能力执行失败，本次运行已停止。",
        }
        return messages.get(result.status.value, "本次运行已停止。")

    @staticmethod
    def _last_result(context: ExecutionContext) -> CapabilityResult | None:
        if not context.step_results:
            return None
        return next(reversed(context.step_results.values()))

    @classmethod
    def _artifact_error_response(
        cls,
        error: ArtifactFlowError,
        *,
        goal: Goal | None = None,
        context: ExecutionContext | None = None,
    ) -> BusinessAgentResponse:
        if error.code in {"INPUT_REQUIRED", "INPUT_AMBIGUOUS"}:
            return BusinessAgentResponse(
                status=BusinessAgentStatus.CLARIFICATION_REQUIRED,
                goal=context.goal if context is not None else goal,
                plan=context.current_plan if context is not None else None,
                execution_context=context,
                last_result=cls._last_result(context) if context is not None else None,
                question="请补充明确对象后重新提交完整目标。",
                missing_information=error.missing_information,
            )
        return BusinessAgentResponse(
            status=BusinessAgentStatus.FAILED,
            goal=context.goal if context is not None else goal,
            plan=context.current_plan if context is not None else None,
            execution_context=context,
            last_result=cls._last_result(context) if context is not None else None,
            error=error.code,
            message=error.message,
            missing_information=error.missing_information,
        )

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
