"""Application-level management agent built around an observable Agent Loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from typing import Any

from agent import AgentEvent, AgentLoop, AgentTrace
from model import ChatModel

from .data_repository import BusinessDataRepository
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .tools import ToolContext, discover_tools


@dataclass(slots=True)
class ManageAgentResult:
    """A generic agent outcome; domain products remain tool observations."""

    answer: str
    status: str
    stop_reason: str | None
    artifacts: list[dict[str, Any]]
    trace: AgentTrace

    def to_dict(self, *, include_trace: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "answer": self.answer,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "artifacts": self.artifacts,
        }
        if include_trace:
            result["trace"] = asdict(self.trace)
        return result


class ManageAgentRun:
    """One isolated trace consisting of one or more model/tool turns."""

    def __init__(
        self,
        *,
        loop: AgentLoop,
        context: ToolContext,
        trace: AgentTrace,
        messages: list[dict[str, Any]],
    ) -> None:
        self._loop = loop
        self._context = context
        self.trace = trace
        self._messages = messages
        self._started = False

    async def events(self) -> AsyncIterator[AgentEvent]:
        if self._started:
            raise RuntimeError("An agent run can only be consumed once")
        self._started = True
        async for event in self._loop.events(self._messages, trace=self.trace):
            yield event

    def result(self) -> ManageAgentResult:
        if not self._started or self.trace.status == "running":
            raise RuntimeError("The agent run has not finished")
        answer = next(
            (
                turn.output_text
                for turn in reversed(self.trace.turns)
                if turn.kind == "final" and turn.output_text.strip()
            ),
            "",
        )
        return ManageAgentResult(
            answer=answer,
            status=self.trace.status,
            stop_reason=self.trace.stop_reason,
            artifacts=list(self._context.artifacts),
            trace=self.trace,
        )


class ManageAgent:
    """Create autonomous, observable runs for management-domain requests."""

    def __init__(
        self,
        *,
        model: ChatModel,
        model_name: str,
        repository: BusinessDataRepository,
        max_tool_turns: int = 8,
    ) -> None:
        self._model = model
        self._model_name = model_name
        self._repository = repository
        self._max_tool_turns = max_tool_turns

    def create_run(
        self,
        *,
        user_message: str,
        data_source_id: str,
    ) -> ManageAgentRun:
        if not user_message.strip():
            raise ValueError("user_message must not be empty")
        context = ToolContext(self._repository)
        tools = discover_tools(context)
        trace = AgentTrace()
        loop = AgentLoop(
            model=self._model,
            model_name=self._model_name,
            tools=tools,
            max_tool_turns=self._max_tool_turns,
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(
                    user_message,
                    data_source_id=data_source_id,
                ),
            },
        ]
        return ManageAgentRun(
            loop=loop,
            context=context,
            trace=trace,
            messages=messages,
        )

    async def run(
        self,
        *,
        user_message: str,
        data_source_id: str,
    ) -> ManageAgentResult:
        run = self.create_run(
            user_message=user_message,
            data_source_id=data_source_id,
        )
        async for _ in run.events():
            pass
        return run.result()
