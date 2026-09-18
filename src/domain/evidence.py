"""Traceable evidence used to support, limit, or contradict domain judgments."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Mapping


class EvidenceType(StrEnum):
    CUSTOMER_FACT = "customer_fact"
    PRODUCT_FACT = "product_fact"
    BUSINESS_FACT = "business_fact"
    RULE_RESULT = "rule_result"
    MODEL_SIGNAL = "model_signal"
    EXPERIENCE = "experience"


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    source_id: str
    source_type: str
    version: str | None = None
    retrieved_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("Evidence source_id is required")
        if not self.source_type:
            raise ValueError("Evidence source_type is required")


@dataclass(frozen=True, slots=True)
class EffectivePeriod:
    start_at: date | None = None
    end_at: date | None = None

    def __post_init__(self) -> None:
        if self.start_at and self.end_at and self.start_at > self.end_at:
            raise ValueError("Evidence effective period start_at must not be after end_at")


@dataclass(frozen=True, slots=True)
class EvidenceQuality:
    confidence: float | None = None
    completeness: float | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        for name in ("confidence", "completeness"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"Evidence quality {name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    evidence_type: EvidenceType
    summary: str
    source: EvidenceSource
    payload: Mapping[str, Any] | None = None
    effective_period: EffectivePeriod | None = None
    quality: EvidenceQuality | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("evidence_id is required")
        if not self.summary.strip():
            raise ValueError("Evidence summary is required")
