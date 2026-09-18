"""Versioned business plans with lightweight dependency validation only."""

from dataclasses import dataclass, replace
from enum import StrEnum

from .refs import GoalRef


class PlanStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class PlanStepStatus(StrEnum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ControlPointType(StrEnum):
    RULE_CHECK = "rule_check"
    USER_CONFIRMATION = "user_confirmation"


@dataclass(frozen=True, slots=True)
class ContextRef:
    reference_type: str
    reference_id: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ControlPoint:
    control_point_id: str
    control_point_type: ControlPointType
    reason: str


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    capability_id: str
    status: PlanStepStatus = PlanStepStatus.PLANNED
    depends_on: tuple[str, ...] = ()
    context_refs: tuple[ContextRef, ...] = ()
    control_points: tuple[ControlPoint, ...] = ()

    def __post_init__(self) -> None:
        if not self.step_id or not self.capability_id:
            raise ValueError("Plan step_id and capability_id are required")
        if self.step_id in self.depends_on:
            raise ValueError("A plan step cannot depend on itself")


@dataclass(frozen=True, slots=True)
class Plan:
    plan_id: str
    version: int
    goal_ref: GoalRef
    status: PlanStatus
    steps: tuple[PlanStep, ...]
    supersedes_version: int | None = None

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ValueError("plan_id is required")
        if self.version < 1:
            raise ValueError("Plan version must be at least 1")
        if self.supersedes_version is not None and self.supersedes_version >= self.version:
            raise ValueError("supersedes_version must be lower than plan version")
        self._validate_dependencies()

    def _validate_dependencies(self) -> None:
        steps_by_id = {step.step_id: step for step in self.steps}
        if len(steps_by_id) != len(self.steps):
            raise ValueError("Plan step_id values must be unique")
        for step in self.steps:
            missing = set(step.depends_on) - steps_by_id.keys()
            if missing:
                raise ValueError(
                    f"Plan step {step.step_id!r} depends on unknown step(s): {sorted(missing)!r}"
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

        for step in self.steps:
            visit(step.step_id)

    def revise(self, *, steps: tuple[PlanStep, ...], status: PlanStatus = PlanStatus.ACTIVE) -> "Plan":
        """Create a replacement Plan version without mutating the old plan."""
        return replace(
            self,
            version=self.version + 1,
            status=status,
            steps=steps,
            supersedes_version=self.version,
        )
