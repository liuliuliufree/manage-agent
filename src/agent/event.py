"""Structured events emitted while an agent trace is running."""

from dataclasses import dataclass
from typing import Literal

from openai.types.chat import ChatCompletionChunk

from .trace import AgentTrace, AgentTurn, ToolExecution


AgentEventType = Literal[
    "trace_start",
    "turn_start",
    "model_end",
    "tool_end",
    "model_chunk",
    "text_delta",
    "thinking_delta",
    "tool_call_delta",
    "tool_start",
    "turn_end",
    "trace_end",
]


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One observable change within an agent trace."""

    type: AgentEventType
    trace: AgentTrace
    turn: AgentTurn | None = None
    tool_execution: ToolExecution | None = None
    chunk: ChatCompletionChunk | None = None
    delta: str | None = None
    tool_call_index: int | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_title: str | None = None
    tool_arguments: str | None = None
