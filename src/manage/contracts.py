"""Structured products returned by management-analysis capabilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResultMetadata:
    data_source_id: str
    data_source_version: str
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
