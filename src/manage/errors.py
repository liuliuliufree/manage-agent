"""Stable errors raised by the management-analysis business layer."""


class ManageError(Exception):
    """Base class for expected management-analysis failures."""


class DataSourceNotFoundError(ManageError):
    """The requested data source is not available."""


class DataSourceError(ManageError):
    """The source facts are incomplete or inconsistent."""


class BusinessRuleError(ManageError):
    """A required versioned business rule is missing or invalid."""


class OpportunityNotFoundError(ManageError):
    """The requested opportunity is not defined in the data source."""


class CustomerNotFoundError(ManageError):
    """The requested customer is not defined in the data source."""
