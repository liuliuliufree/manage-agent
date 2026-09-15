"""Acts 1-3 management-analysis business package."""

from .contracts import (
    ActsAnalysisResult,
    BusinessContext,
    CustomerDecision,
    OpportunityAnalysis,
    OpportunityMetric,
    ResultMetadata,
    SegmentResult,
)
from .errors import (
    BusinessRuleError,
    CustomerNotFoundError,
    ManageError,
    OpportunityNotFoundError,
    ScenarioDataError,
    ScenarioNotFoundError,
)
from .prompts import SYSTEM_PROMPT, build_task_prompt
from .repository import ScenarioRepository, ScenarioSnapshot
from .service import (
    ANNIVERSARY_OPPORTUNITY,
    FAMILY_OPPORTUNITY,
    MEDICAL_OPPORTUNITY,
    ManageService,
)
from .tools import ManageToolSession
from .workflow import ActsOneToThreeAgent

__all__ = [
    "ANNIVERSARY_OPPORTUNITY",
    "ActsAnalysisResult",
    "ActsOneToThreeAgent",
    "BusinessContext",
    "BusinessRuleError",
    "CustomerDecision",
    "CustomerNotFoundError",
    "FAMILY_OPPORTUNITY",
    "MEDICAL_OPPORTUNITY",
    "ManageError",
    "ManageService",
    "ManageToolSession",
    "OpportunityAnalysis",
    "OpportunityMetric",
    "OpportunityNotFoundError",
    "ResultMetadata",
    "SYSTEM_PROMPT",
    "ScenarioDataError",
    "ScenarioNotFoundError",
    "ScenarioRepository",
    "ScenarioSnapshot",
    "SegmentResult",
    "build_task_prompt",
]
