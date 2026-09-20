"""Lightweight deterministic validation for M2-Lite plans."""

from collections.abc import Mapping

from src.domain import CapabilityStatus, Plan

from .execution_context import ExecutionContext


_SUCCESS_LIKE = frozenset(
    {
        CapabilityStatus.SUCCESS,
        CapabilityStatus.PARTIAL_SUCCESS,
    }
)


def validate_plan(
    plan: Plan,
    capability_catalog: Mapping[str, object],
) -> None:
    """Validate only catalog membership and basic step dependencies."""

    known_capabilities = set(capability_catalog)
    unknown_capabilities = sorted(
        {
            step.capability_id
            for step in plan.steps
            if step.capability_id not in known_capabilities
        }
    )
    if unknown_capabilities:
        raise ValueError(
            f"Plan contains unknown capability(s): {unknown_capabilities!r}"
        )

    steps_by_id = {step.step_id: step for step in plan.steps}
    if len(steps_by_id) != len(plan.steps):
        raise ValueError("Plan step_id values must be unique")

    for step in plan.steps:
        missing = sorted(set(step.depends_on) - steps_by_id.keys())
        if missing:
            raise ValueError(
                f"Plan step {step.step_id!r} depends on unknown step(s): {missing!r}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError("Plan steps must not form a dependency cycle")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in steps_by_id[step_id].depends_on:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in steps_by_id:
        visit(step_id)


def validate_replan(
    old_plan: Plan,
    new_plan: Plan,
    context: ExecutionContext,
) -> None:
    """Prevent retained completed step IDs from changing capability identity."""

    old_steps = {step.step_id: step for step in old_plan.steps}
    for new_step in new_plan.steps:
        old_step = old_steps.get(new_step.step_id)
        result = context.step_results.get(new_step.step_id)
        if (
            old_step is not None
            and result is not None
            and result.status in _SUCCESS_LIKE
            and new_step.capability_id != old_step.capability_id
        ):
            raise ValueError(
                f"Completed step {new_step.step_id!r} cannot change capability_id"
            )
