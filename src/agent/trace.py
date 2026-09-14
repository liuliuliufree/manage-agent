"""Observable state produced by one agent run."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4


TraceStatus = Literal["running", "completed", "failed", "cancelled"]
TurnStatus = Literal["running", "completed", "failed", "cancelled"]
TurnKind = Literal["model", "tool", "final"]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ToolExecution:
    """One tool call and the result returned to the model."""

    tool_call_id: str
    name: str
    arguments: str
    result: str
    is_error: bool


@dataclass(slots=True)
class AgentTurn:
    """One model call plus every tool execution requested by that call."""

    index: int
    kind: TurnKind
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    status: TurnStatus = "running"
    assistant_message: dict[str, Any] | None = None
    tool_executions: list[ToolExecution] = field(default_factory=list)
    output_text: str = ""
    thinking_text: str = ""
    finish_reason: str | None = None
    error: str | None = None


@dataclass(slots=True)
class AgentTrace:
    """The complete observable record from agent start to agent end."""

    id: str = field(default_factory=lambda: uuid4().hex)
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    status: TraceStatus = "running"
    turns: list[AgentTurn] = field(default_factory=list)
    stop_reason: str | None = None
    error: str | None = None

    def start_turn(self, kind: TurnKind) -> AgentTurn:
        turn = AgentTurn(index=len(self.turns) + 1, kind=kind)
        self.turns.append(turn)
        return turn
