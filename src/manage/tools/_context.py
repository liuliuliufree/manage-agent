"""Per-trace dependencies and observations shared by business tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..data_repository import BusinessDataRepository
    from ..service import ManageService


@dataclass(slots=True)
class ToolContext:
    """Keep tool state scoped to one agent trace, never across user requests."""

    repository: BusinessDataRepository
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    _services: dict[str, ManageService] = field(default_factory=dict, repr=False)

    def service(self, data_source_id: str) -> ManageService:
        service = self._services.get(data_source_id)
        if service is None:
            from ..service import ManageService

            service = ManageService(self.repository.load(data_source_id))
            self._services[data_source_id] = service
        return service

    def observe(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        self.artifacts.append(
            {"tool_name": tool_name, "arguments": dict(arguments), "result": result}
        )
        return result
