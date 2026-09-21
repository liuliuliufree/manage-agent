"""Stable business-capability request and result contracts.

These are envelopes only. They deliberately do not execute capabilities or
depend on the Tool, Trace, AgentLoop, or ChatModel implementations.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from .goal import MissingInformation
from .refs import GoalRef, PlanRef


class CapabilityStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    NEED_INFORMATION = "need_information"
    BLOCKED = "blocked"
    NO_RESULT = "no_result"
    FAILED = "failed"


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    DEPENDENCY = "dependency"
    TIMEOUT = "timeout"
    ACCESS = "access"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    capability_id: str
    name: str
    description: str
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.capability_id or not self.name or not self.description:
            raise ValueError("Capability definition id, name, and description are required")


@dataclass(frozen=True, slots=True)
class ObjectScope:
    scope_type: str
    object_refs: tuple[str, ...] = ()
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ActorContext:
    actor_id: str | None
    channel_id: str | None
    trusted_source: str

    def __post_init__(self) -> None:
        if not self.trusted_source:
            raise ValueError("ActorContext trusted_source is required")


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    request_id: str
    capability_id: str
    goal_ref: GoalRef
    actor_context: ActorContext
    plan_ref: PlanRef | None = None
    object_scope: ObjectScope | None = None
    input_refs: tuple[str, ...] = ()
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("Capability request_id is required")
        if not self.capability_id:
            raise ValueError("Capability capability_id is required")


@dataclass(frozen=True, slots=True)
class CapabilityOutput:
    output_id: str
    output_type: str
    summary: str
    payload: Mapping[str, Any] | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultQuality:
    confidence: float | None = None
    completeness: float | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        for name in ("confidence", "completeness"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"Result quality {name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class CapabilityExecutionMeta:
    trace_id: str | None = None
    implementation_ref: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.started_at and self.completed_at and self.started_at > self.completed_at:
            raise ValueError("Capability execution completed_at must not precede started_at")


@dataclass(frozen=True, slots=True)
class CapabilityError:
    category: ErrorCategory
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    request_id: str
    capability_id: str
    status: CapabilityStatus
    outputs: tuple[CapabilityOutput, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    rule_result_refs: tuple[str, ...] = ()
    missing_information: tuple[MissingInformation, ...] = ()
    errors: tuple[CapabilityError, ...] = ()
    limitations: tuple[str, ...] = ()
    quality: ResultQuality | None = None
    execution_meta: CapabilityExecutionMeta | None = None

    def __post_init__(self) -> None:
        if not self.request_id or not self.capability_id:
            raise ValueError("Capability result request_id and capability_id are required")
        if self.status is CapabilityStatus.FAILED and not self.errors:
            raise ValueError("FAILED capability result requires at least one error")
        if self.status is CapabilityStatus.BLOCKED and not self.rule_result_refs:
            raise ValueError("BLOCKED capability result requires at least one rule_result_ref")
        if self.status is CapabilityStatus.NEED_INFORMATION and not self.missing_information:
            raise ValueError("NEED_INFORMATION result requires missing_information")
        if self.status is CapabilityStatus.SUCCESS and self.errors:
            raise ValueError("SUCCESS capability result must not contain errors")
        if self.status is CapabilityStatus.PARTIAL_SUCCESS and not (
            self.errors or self.missing_information or self.limitations
        ):
            raise ValueError(
                "PARTIAL_SUCCESS requires errors, missing_information, or limitations"
            )
