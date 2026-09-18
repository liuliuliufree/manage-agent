"""Stable references between versioned domain artifacts."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GoalRef:
    goal_id: str
    version: int

    def __post_init__(self) -> None:
        if not self.goal_id:
            raise ValueError("goal_id is required")
        if self.version < 1:
            raise ValueError("Goal reference version must be at least 1")


@dataclass(frozen=True, slots=True)
class PlanRef:
    plan_id: str
    version: int

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ValueError("plan_id is required")
        if self.version < 1:
            raise ValueError("Plan reference version must be at least 1")
