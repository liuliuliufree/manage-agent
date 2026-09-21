"""Contracts that describe what an operator wants to achieve."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class Metric:
    code: str
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class Target:
    value: Decimal | str
    unit: str | None = None
    comparator: Literal["at_least", "at_most", "equal_to", "improve"] = "at_least"


@dataclass(frozen=True, slots=True)
class TimeHorizon:
    raw_expression: str | None = None
    start_at: date | None = None
    end_at: date | None = None

    def __post_init__(self) -> None:
        if self.start_at and self.end_at and self.start_at > self.end_at:
            raise ValueError("Time horizon start_at must not be after end_at")


@dataclass(frozen=True, slots=True)
class AudienceScope:
    scope_type: str
    scope_reference: str | None = None
    raw_expression: str | None = None


@dataclass(frozen=True, slots=True)
class ProductOrNeedContext:
    products: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()
    raw_expression: str | None = None


@dataclass(frozen=True, slots=True)
class ChannelAndActor:
    channel_id: str | None = None
    actor_id: str | None = None
    context_source: str | None = None


@dataclass(frozen=True, slots=True)
class Constraint:
    code: str
    description: str
    source: str = "request_or_context"


@dataclass(frozen=True, slots=True)
class MissingInformation:
    field: str
    reason: str
    impact: str
    required_before_execution: bool = False


@dataclass(frozen=True, slots=True)
class Assumption:
    description: str
    reason: str
    revisable: bool = True


@dataclass(frozen=True, slots=True)
class Goal:
    """An immutable, versioned statement of intent, not an execution plan."""

    goal_id: str
    version: int
    original_request: str
    goal_type: str
    metric: Metric | None = None
    target: Target | None = None
    time_horizon: TimeHorizon | None = None
    audience_scope: AudienceScope | None = None
    product_or_need_context: ProductOrNeedContext | None = None
    channel_and_actor: ChannelAndActor | None = None
    constraints: tuple[Constraint, ...] = ()
    missing_information: tuple[MissingInformation, ...] = ()
    assumptions: tuple[Assumption, ...] = ()

    def __post_init__(self) -> None:
        if not self.goal_id:
            raise ValueError("goal_id is required")
        if self.version < 1:
            raise ValueError("Goal version must be at least 1")
        if not self.original_request.strip():
            raise ValueError("original_request is required")
        if not self.goal_type.strip():
            raise ValueError("goal_type is required")

    def revise(self, *, original_request: str | None = None, **changes: object) -> "Goal":
        """Create a new immutable version while retaining its creation request.

        ``original_request`` remains an accepted keyword temporarily for callers
        from the earlier contract.  A revision request belongs in runtime audit
        data, not in the Goal identity, so it intentionally never replaces the
        first request recorded on this Goal.
        """
        if "goal_id" in changes or "version" in changes:
            raise ValueError("Goal identity and version are managed by revise()")
        return replace(
            self,
            version=self.version + 1,
            **changes,
        )
