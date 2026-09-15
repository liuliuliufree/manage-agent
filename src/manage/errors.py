"""Stable errors raised by the management-analysis business layer."""


class ManageError(Exception):
    """Base class for expected management-analysis failures."""


class ScenarioNotFoundError(ManageError):
    """The requested scenario is not available."""


class ScenarioDataError(ManageError):
    """The scenario source facts are incomplete or inconsistent."""


class BusinessRuleError(ManageError):
    """A required versioned business rule is missing or invalid."""


class OpportunityNotFoundError(ManageError):
    """The requested opportunity is not defined in the scenario."""


class CustomerNotFoundError(ManageError):
    """The requested customer is not defined in the scenario."""
