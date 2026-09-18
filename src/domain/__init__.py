"""Business-domain contracts for the intelligent operations agent.

This package intentionally has no dependency on the agent or model runtimes.
"""

from .capability import (
    ActorContext,
    CapabilityConstraint,
    CapabilityContext,
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
from .evidence import Evidence, EvidenceQuality, EvidenceSource, EvidenceType, EffectivePeriod
from .goal import (
    Assumption,
    AudienceScope,
    ChannelAndActor,
    Constraint,
    Goal,
    Metric,
    MissingInformation,
    ProductOrNeedContext,
    SuccessCriterion,
    Target,
    TimeHorizon,
)
from .opportunity import (
    CandidateLogic,
    EvidenceLink,
    EvidenceRole,
    GoalContribution,
    GoalLink,
    NextActionHint,
    Opportunity,
    OpportunityCondition,
    OpportunityPriority,
    OpportunityValidity,
    PriorityFactor,
)
from .plan import ControlPoint, ControlPointType, ContextRef, Plan, PlanStatus, PlanStep, PlanStepStatus
from .refs import GoalRef, PlanRef

__all__ = [
    "ActorContext", "Assumption", "AudienceScope", "CandidateLogic", "CapabilityConstraint", "CapabilityContext",
    "CapabilityDefinition", "CapabilityError", "CapabilityExecutionMeta", "CapabilityOutput",
    "CapabilityRequest", "CapabilityResult", "CapabilityStatus", "ChannelAndActor", "Constraint",
    "ContextRef", "ControlPoint", "ControlPointType", "EffectivePeriod", "ErrorCategory", "Evidence",
    "EvidenceLink", "EvidenceQuality", "EvidenceRole", "EvidenceSource", "EvidenceType", "Goal",
    "GoalContribution", "GoalLink", "GoalRef", "Metric", "MissingInformation", "NextActionHint",
    "ObjectScope", "Opportunity", "OpportunityCondition", "OpportunityPriority", "OpportunityValidity",
    "Plan", "PlanRef", "PlanStatus", "PlanStep", "PlanStepStatus", "PriorityFactor",
    "ProductOrNeedContext", "ResultQuality", "SuccessCriterion", "Target", "TimeHorizon",
]
