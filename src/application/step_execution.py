"""Minimal mapping and execution for one plan step."""

from uuid import uuid4

from src.domain import (
    ActorContext,
    CapabilityRequest,
    CapabilityResult,
    GoalRef,
    PlanRef,
    PlanStep,
)

from .capability_executor import CapabilityExecutor
from .execution_context import ExecutionContext


def _input_refs(known_context: dict[str, object]) -> tuple[str, ...]:
    """Keep only typed references from application context in the request envelope."""
    refs: list[str] = []
    for key, values in known_context.items():
        if not key.endswith("_refs") or not isinstance(values, (list, tuple)):
            continue
        reference_type = key.removesuffix("_refs")
        refs.extend(
            f"{reference_type}:{value.strip()}"
            for value in values
            if isinstance(value, str) and value.strip()
        )
    return tuple(refs)


def build_capability_request(
    step: PlanStep,
    context: ExecutionContext,
) -> CapabilityRequest:
    """Map a plan step and its execution context to the existing request contract."""
    channel_and_actor = context.goal.channel_and_actor
    return CapabilityRequest(
        request_id=f"capability_request_{uuid4().hex}",
        capability_id=step.capability_id,
        goal_ref=GoalRef(
            goal_id=context.goal.goal_id,
            version=context.goal.version,
        ),
        plan_ref=PlanRef(
            plan_id=context.current_plan.plan_id,
            version=context.current_plan.version,
        ),
        actor_context=ActorContext(
            actor_id=(
                channel_and_actor.actor_id if channel_and_actor is not None else None
            ),
            channel_id=(
                channel_and_actor.channel_id if channel_and_actor is not None else None
            ),
            trusted_source=(
                channel_and_actor.context_source
                if channel_and_actor is not None
                and channel_and_actor.context_source
                else "execution_context.goal"
            ),
        ),
        input_refs=_input_refs(context.known_context),
    )


def execute_step(
    step: PlanStep,
    context: ExecutionContext,
    executor: CapabilityExecutor,
) -> CapabilityResult:
    """Execute one plan step and record its result in the execution context."""
    request = build_capability_request(step=step, context=context)
    result = executor.execute(request)
    context.record_result(step.step_id, result)
    return result
