"""Contracts for evidence-grounded operating opportunities."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .refs import GoalRef


@dataclass(frozen=True, slots=True)
class GoalLink:
    """An Opportunity's explicit reference to the Goal version it serves."""

    goal_id: str
    version: int

    def __post_init__(self) -> None:
        # Reuse the canonical identity validation without making Opportunity
        # depend on a runtime artifact.
        GoalRef(self.goal_id, self.version)


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
class GoalContribution:
    contribution_type: str
    description: str
    estimated_value: str | None = None


@dataclass(frozen=True, slots=True)
class OpportunityCondition:
    description: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class CandidateLogic:
    """Business-facing candidate logic; it is not a query or permission decision."""

    description: str
    conditions: tuple[OpportunityCondition, ...] = ()


@dataclass(frozen=True, slots=True)
class PriorityFactor:
    factor: str
    explanation: str
    contribution: float | None = None


@dataclass(frozen=True, slots=True)
class OpportunityPriority:
    level: str
    score: float | None = None
    factors: tuple[PriorityFactor, ...] = ()

    def __post_init__(self) -> None:
        if not self.level:
            raise ValueError("Opportunity priority level is required")
        if not self.factors:
            raise ValueError("Opportunity priority requires at least one explanatory factor")


@dataclass(frozen=True, slots=True)
class OpportunityValidity:
    status: str = "active"
    effective_from: date | None = None
    effective_until: date | None = None

    def __post_init__(self) -> None:
        if self.effective_from and self.effective_until and self.effective_from > self.effective_until:
            raise ValueError("Opportunity validity effective_from must not be after effective_until")


@dataclass(frozen=True, slots=True)
class NextActionHint:
    description: str
    rationale: str | None = None


@dataclass(frozen=True, slots=True)
class Opportunity:
    opportunity_id: str
    goal_link: GoalLink
    opportunity_type: str
    problem_statement: str
    evidence_links: tuple[EvidenceLink, ...]
    goal_contributions: tuple[GoalContribution, ...] = ()
    conditions: tuple[OpportunityCondition, ...] = ()
    candidate_logic: CandidateLogic | None = None
    priority: OpportunityPriority | None = None
    validity: OpportunityValidity | None = None
    next_action_hint: NextActionHint | None = None

    def __post_init__(self) -> None:
        if not self.opportunity_id:
            raise ValueError("opportunity_id is required")
        if not self.opportunity_type:
            raise ValueError("opportunity_type is required")
        if not self.problem_statement.strip():
            raise ValueError("Opportunity problem_statement is required")
        if not self.evidence_links:
            raise ValueError("A formal Opportunity requires at least one EvidenceLink")
