"""Minimal continuation decisions after a capability execution."""

from enum import StrEnum

from src.domain import CapabilityResult, CapabilityStatus, Plan

from .execution_context import ExecutionContext
from .step_resolution import get_next_ready_step


class ContinuationAction(StrEnum):
    CONTINUE = "continue"
    REPLAN = "replan"
    ASK_USER = "ask_user"
    FINISH = "finish"
    STOP = "stop"


SUCCESS_LIKE = frozenset(
    {
        CapabilityStatus.SUCCESS,
        CapabilityStatus.PARTIAL_SUCCESS,
    }
)


def is_plan_finished(plan: Plan, context: ExecutionContext) -> bool:
    """Return whether every plan step has a success-like result."""
    return all(
        (result := context.step_results.get(step.step_id)) is not None
        and result.status in SUCCESS_LIKE
        for step in plan.steps
    )


def decide_continuation(
    plan: Plan,
    context: ExecutionContext,
    last_result: CapabilityResult,
) -> ContinuationAction:
    """Choose the next runtime action from the latest capability result."""
    if last_result.status is CapabilityStatus.NO_RESULT:
        return ContinuationAction.REPLAN
    if last_result.status is CapabilityStatus.NEED_INFORMATION:
        return ContinuationAction.ASK_USER
    if last_result.status in (
        CapabilityStatus.BLOCKED,
        CapabilityStatus.FAILED,
    ):
        return ContinuationAction.STOP

    if last_result.status in SUCCESS_LIKE:
        if get_next_ready_step(plan, context) is not None:
            return ContinuationAction.CONTINUE
        if is_plan_finished(plan, context):
            return ContinuationAction.FINISH

    return ContinuationAction.STOP
