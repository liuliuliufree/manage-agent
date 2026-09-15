"""Structured products returned by the acts 1-3 business capabilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ResultMetadata:
    scenario_id: str
    scenario_version: str
    baseline_at: str
    data_mode: str
    data_definition_version: str
    rule_version: str


@dataclass(frozen=True, slots=True)
class BusinessContext:
    metadata: ResultMetadata
    request: dict[str, Any]
    system_rules: dict[str, dict[str, int | float | str]]
    data_scope: dict[str, int]
    data_quality_notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OpportunityMetric:
    opportunity_id: str
    name: str
    definition_version: str
    customer_count: int
    metrics: dict[str, float]
    composite_score: float
    rank: int
    recommended: bool
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OpportunityAnalysis:
    metadata: ResultMetadata
    opportunities: tuple[OpportunityMetric, ...]
    recommended_opportunity_id: str
    scoring_weights: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CustomerSummary:
    customer_id: str
    disposition: str
    primary_reason: str
    priority_rank: int | None = None
    priority_score: int | None = None
    explanation_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SegmentResult:
    metadata: ResultMetadata
    opportunity_id: str
    opportunity_name: str
    funnel: dict[str, int]
    exclusion_counts: dict[str, int]
    priority_customers: tuple[CustomerSummary, ...]
    exclusion_samples: dict[str, CustomerSummary]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CustomerDecision:
    metadata: ResultMetadata
    opportunity_id: str
    customer_id: str
    disposition: str
    primary_reason: str
    opportunity_evidence: tuple[dict[str, Any], ...]
    hard_rule_checks: tuple[dict[str, Any], ...]
    priority_score: int | None
    priority_rank: int | None
    score_contributions: tuple[dict[str, Any], ...]
    allowed_actions: tuple[str, ...]
    prohibited_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ActsAnalysisResult:
    """End-to-end Agent result plus deterministic business artifacts."""

    answer: str
    business_context: dict[str, Any]
    opportunity_analysis: dict[str, Any]
    segment_result: dict[str, Any]
    customer_decisions: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    degradation_reason: str | None = None
    trace: Any | None = None

    def to_dict(self, *, include_trace: bool = False) -> dict[str, Any]:
        result = {
            "answer": self.answer,
            "business_context": self.business_context,
            "opportunity_analysis": self.opportunity_analysis,
            "segment_result": self.segment_result,
            "customer_decisions": self.customer_decisions,
            "degraded": self.degraded,
            "degradation_reason": self.degradation_reason,
        }
        if include_trace:
            result["trace"] = self.trace
        return result
