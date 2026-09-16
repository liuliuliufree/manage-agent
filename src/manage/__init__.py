"""Management-domain capabilities and the application agent."""

from .agent import ManageAgent, ManageAgentResult, ManageAgentRun
from .contracts import (
    BusinessContext,
    CustomerDecision,
    OpportunityAnalysis,
    OpportunityMetric,
    ResultMetadata,
    SegmentResult,
)
from .data_repository import BusinessDataRepository, BusinessDataSnapshot
from .errors import (
    BusinessRuleError,
    CustomerNotFoundError,
    ManageError,
    OpportunityNotFoundError,
    DataSourceError,
    DataSourceNotFoundError,
)
from .service import (
    ANNIVERSARY_OPPORTUNITY,
    FAMILY_OPPORTUNITY,
    MEDICAL_OPPORTUNITY,
    ManageService,
)

__all__ = [
    "ANNIVERSARY_OPPORTUNITY",
    "BusinessContext",
    "BusinessDataRepository",
    "BusinessDataSnapshot",
    "BusinessRuleError",
    "CustomerDecision",
    "CustomerNotFoundError",
    "FAMILY_OPPORTUNITY",
    "MEDICAL_OPPORTUNITY",
    "ManageAgent",
    "ManageAgentResult",
    "ManageAgentRun",
    "ManageError",
    "ManageService",
    "OpportunityAnalysis",
    "OpportunityMetric",
    "OpportunityNotFoundError",
    "ResultMetadata",
    "DataSourceError",
    "DataSourceNotFoundError",
    "SegmentResult",
]
