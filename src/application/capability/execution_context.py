"""Minimal mutable state shared across capability execution steps."""

from dataclasses import dataclass, field
from typing import Any

from src.domain import CapabilityResult, Goal, GoalRef, Plan, PlanRef

from .artifact_flow import PublishedArtifact
from .artifact_store import ArtifactStore


@dataclass(slots=True)
class ExecutionContext:
    goal: Goal
    current_plan: Plan
    known_context: dict[str, Any] = field(default_factory=dict)
    step_results: dict[str, CapabilityResult] = field(default_factory=dict)
    artifact_store: ArtifactStore = field(default_factory=ArtifactStore)
    initial_refs: tuple[str, ...] = ()
    published_artifacts: dict[str, PublishedArtifact] = field(default_factory=dict)
    _goal_ref: GoalRef = field(init=False, repr=False)
    _plan_ref: PlanRef = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._goal_ref = GoalRef(self.goal.goal_id, self.goal.version)
        self._plan_ref = PlanRef(self.current_plan.plan_id, self.current_plan.version)

    @property
    def bound_goal_ref(self) -> GoalRef:
        return self._goal_ref

    @property
    def bound_plan_ref(self) -> PlanRef:
        return self._plan_ref

    def record_result(self, step_id: str, result: CapabilityResult) -> None:
        self.step_results[step_id] = result
