"""Build, execute, validate, and publish one capability step."""

from __future__ import annotations

from uuid import uuid4

from src.domain import (
    ActorContext,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    GoalRef,
    PlanRef,
    PlanStep,
)

from .artifact_flow import (
    ArtifactFlowError,
    CapabilityIO,
    PublishedArtifact,
    resolve_input_refs,
)
from .artifact_store import split_artifact_ref
from .capability_executor import CapabilityExecutor
from .execution_context import ExecutionContext


def _check_context(step: PlanStep, context: ExecutionContext) -> None:
    current_goal_ref = GoalRef(context.goal.goal_id, context.goal.version)
    if current_goal_ref != context.bound_goal_ref:
        raise ArtifactFlowError(
            "ARTIFACT_GOAL_CHANGED", "Goal changed during artifact execution."
        )
    current_plan_ref = PlanRef(
        context.current_plan.plan_id, context.current_plan.version
    )
    if current_plan_ref != context.bound_plan_ref:
        raise ArtifactFlowError(
            "ARTIFACT_CONTEXT_INVALID", "Plan changed during artifact execution."
        )
    plan_step = next(
        (item for item in context.current_plan.steps if item.step_id == step.step_id),
        None,
    )
    if plan_step != step or step.step_id in context.step_results:
        raise ArtifactFlowError("STEP_NOT_READY", "Plan step is not ready.")
    for dependency in step.depends_on:
        result = context.step_results.get(dependency)
        if result is None or result.status is not CapabilityStatus.SUCCESS:
            raise ArtifactFlowError("STEP_NOT_READY", "Plan step is not ready.")


def build_capability_request(
    step: PlanStep,
    context: ExecutionContext,
    *,
    io: CapabilityIO,
) -> CapabilityRequest:
    """Resolve only declared, permitted input artifacts for a ready step."""
    _check_context(step, context)
    channel_and_actor = context.goal.channel_and_actor
    return CapabilityRequest(
        request_id=f"capability_request_{uuid4().hex}",
        capability_id=step.capability_id,
        goal_ref=GoalRef(context.goal.goal_id, context.goal.version),
        plan_ref=PlanRef(context.current_plan.plan_id, context.current_plan.version),
        actor_context=ActorContext(
            actor_id=(
                channel_and_actor.actor_id if channel_and_actor is not None else None
            ),
            channel_id=(
                channel_and_actor.channel_id if channel_and_actor is not None else None
            ),
            trusted_source=(
                channel_and_actor.context_source
                if channel_and_actor is not None and channel_and_actor.context_source
                else "execution_context.goal"
            ),
        ),
        input_refs=resolve_input_refs(step, context, io),
    )


def execute_step(
    step: PlanStep,
    context: ExecutionContext,
    executor: CapabilityExecutor,
    *,
    io: CapabilityIO,
) -> CapabilityResult:
    """Execute once and atomically publish only validated SUCCESS outputs."""
    request = build_capability_request(step, context, io=io)
    result = executor.execute(request)
    if not isinstance(result, CapabilityResult):
        raise ArtifactFlowError("RESULT_INVALID", "Capability returned an invalid result.")
    if (
        result.request_id != request.request_id
        or result.capability_id != request.capability_id
    ):
        raise ArtifactFlowError(
            "RESULT_IDENTITY_MISMATCH",
            "Capability result does not match its request.",
        )
    if result.status is not CapabilityStatus.SUCCESS:
        context.record_result(step.step_id, result)
        return result

    pending: list[PublishedArtifact] = []
    batch_refs: set[str] = set()
    output_type_counts: dict[str, int] = {}
    for output in result.outputs:
        if (
            not isinstance(output.output_type, str)
            or not isinstance(output.output_id, str)
            or not output.output_type
            or not output.output_id
        ):
            raise ArtifactFlowError(
                "OUTPUT_TYPE_INVALID", "Capability output identity is invalid."
            )
        try:
            ref_type, ref_id = split_artifact_ref(
                f"{output.output_type}:{output.output_id}"
            )
        except ArtifactFlowError as exc:
            raise ArtifactFlowError(
                "OUTPUT_TYPE_INVALID", "Capability output identity is invalid."
            ) from exc
        if ref_type not in io.output_types:
            raise ArtifactFlowError(
                "OUTPUT_TYPE_INVALID", "Capability output type is not declared."
            )
        ref = f"{ref_type}:{ref_id}"
        output_type_counts[ref_type] = output_type_counts.get(ref_type, 0) + 1
        if output_type_counts[ref_type] > 1:
            raise ArtifactFlowError(
                "OUTPUT_CARDINALITY_INVALID",
                "Capability returned multiple objects for one output type.",
            )
        if (
            ref in batch_refs
            or ref in context.published_artifacts
            or ref in context.initial_refs
        ):
            raise ArtifactFlowError(
                "ARTIFACT_DUPLICATE", "Capability output reference is duplicated."
            )
        stored = context.artifact_store.get(ref)
        if stored.artifact_type != ref_type:
            raise ArtifactFlowError(
                "ARTIFACT_TYPE_MISMATCH", "Stored output type does not match."
            )
        batch_refs.add(ref)
        pending.append(
            PublishedArtifact(
                ref=ref,
                source_step_id=step.step_id,
                source_request_id=request.request_id,
                source_plan_ref=request.plan_ref,
            )
        )

    context.record_result(step.step_id, result)
    for published in pending:
        context.published_artifacts[published.ref] = published
    return result
