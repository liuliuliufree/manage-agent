"""Minimal mutable state shared across capability execution steps."""

from dataclasses import dataclass, field
from typing import Any

from src.domain import CapabilityResult, Goal, Plan


@dataclass(slots=True)
class ExecutionContext:
    goal: Goal
    current_plan: Plan
    known_context: dict[str, Any] = field(default_factory=dict)
    step_results: dict[str, CapabilityResult] = field(default_factory=dict)

    def record_result(self, step_id: str, result: CapabilityResult) -> None:
        self.step_results[step_id] = result
