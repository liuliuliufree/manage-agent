"""Contracts for evidence-grounded operating opportunities."""

from dataclasses import dataclass
from enum import StrEnum

from .refs import GoalRef


class EvidenceRole(StrEnum):
    SUPPORTS = "supports"
    LIMITS = "limits"
    CONTRADICTS = "contradicts"


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    evidence_id: str
    role: EvidenceRole

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("Evidence link evidence_id is required")


@dataclass(frozen=True, slots=True)
class Opportunity:
    opportunity_id: str
    goal_ref: GoalRef
    opportunity_type: str
    problem_statement: str
    evidence_links: tuple[EvidenceLink, ...]
    priority: str | None = None
    priority_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.opportunity_id:
            raise ValueError("opportunity_id is required")
        if not self.opportunity_type:
            raise ValueError("opportunity_type is required")
        if not self.problem_statement.strip():
            raise ValueError("Opportunity problem_statement is required")
        if not self.evidence_links:
            raise ValueError("A formal Opportunity requires at least one EvidenceLink")
        if (self.priority is None) != (self.priority_reason is None):
            raise ValueError("Opportunity priority and priority_reason must be provided together")
