"""Business-domain contracts for the intelligent operations agent.

This package intentionally has no dependency on the agent or model runtimes.
"""

from .capability import (
    ActorContext,
    CapabilityDefinition,
    CapabilityError,
    CapabilityExecutionMeta,
    CapabilityOutput,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ErrorCategory,
    ObjectScope,
    ResultQuality,
)
from .evidence import Evidence, EvidenceSource, EvidenceType, EffectivePeriod
from .goal import (
    Assumption,
    AudienceScope,
    ChannelAndActor,
    Constraint,
    Goal,
    Metric,
    MissingInformation,
    ProductOrNeedContext,
    Target,
    TimeHorizon,
)
from .opportunity import (
    EvidenceLink,
    EvidenceRole,
    Opportunity,
)
from .plan import Plan, PlanStatus, PlanStep
from .refs import GoalRef, PlanRef

__all__ = [
    "ActorContext", "Assumption", "AudienceScope", "CapabilityDefinition", "CapabilityError", "CapabilityExecutionMeta", "CapabilityOutput",
    "CapabilityRequest", "CapabilityResult", "CapabilityStatus", "ChannelAndActor", "Constraint",
    "EffectivePeriod", "ErrorCategory", "Evidence", "EvidenceLink", "EvidenceRole", "EvidenceSource",
    "EvidenceType", "Goal", "GoalRef", "Metric", "MissingInformation", "ObjectScope", "Opportunity",
    "Plan", "PlanRef", "PlanStatus", "PlanStep", "ProductOrNeedContext", "ResultQuality", "Target",
    "TimeHorizon",
]
