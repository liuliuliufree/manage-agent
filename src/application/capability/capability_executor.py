"""Minimal dispatch for executing registered business capabilities."""

from collections.abc import Callable, Mapping
from typing import TypeAlias

from src.domain import (
    CapabilityError,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ErrorCategory,
)


CapabilityHandler: TypeAlias = Callable[[CapabilityRequest], CapabilityResult]


class CapabilityExecutor:
    """Dispatch a capability request to its registered callable handler."""

    def __init__(self, handlers: Mapping[str, CapabilityHandler]) -> None:
        non_callable = sorted(
            capability_id
            for capability_id, handler in handlers.items()
            if not callable(handler)
        )
        if non_callable:
            raise ValueError(
                f"Capability handler(s) must be callable: {non_callable!r}"
            )
        self._handlers = dict(handlers)

    @property
    def available_capability_ids(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        handler = self._handlers.get(request.capability_id)
        if handler is None:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                status=CapabilityStatus.FAILED,
                errors=(
                    CapabilityError(
                        category=ErrorCategory.DEPENDENCY,
                        code="capability_handler_not_found",
                        message=(
                            "No handler is registered for capability "
                            f"{request.capability_id!r}"
                        ),
                    ),
                ),
            )

        try:
            return handler(request)
        except Exception as exc:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                status=CapabilityStatus.FAILED,
                errors=(
                    CapabilityError(
                        category=ErrorCategory.INTERNAL,
                        code="capability_handler_failed",
                        message=str(exc),
                    ),
                ),
            )
