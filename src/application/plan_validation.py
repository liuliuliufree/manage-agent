"""Lightweight deterministic validation for M2-Lite plans."""

from collections.abc import Mapping

from src.domain import Plan


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
