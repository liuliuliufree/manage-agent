"""Minimal ready-step resolution for a capability plan."""

from src.domain import CapabilityStatus, Plan, PlanStep

from .execution_context import ExecutionContext


def is_step_ready(step: PlanStep, context: ExecutionContext) -> bool:
    """Return whether a step is unexecuted and all dependencies succeeded."""
    if step.step_id in context.step_results:
        return False

    for dependency_id in step.depends_on:
        dependency_result = context.step_results.get(dependency_id)
        if dependency_result is None or dependency_result.status not in (
            CapabilityStatus.SUCCESS,
            CapabilityStatus.PARTIAL_SUCCESS,
        ):
            return False

    return True


def get_next_ready_step(
    plan: Plan,
    context: ExecutionContext,
) -> PlanStep | None:
    """Return the first ready step in plan order, if one exists."""
    for step in plan.steps:
        if is_step_ready(step, context):
            return step
    return None
