"""Agent loop that streams every model turn and its observable events."""

import asyncio
import inspect
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import CompletionCreateParamsBase

from model import ChatModel

from .event import AgentEvent
from .tool import Tool
from .trace import AgentTrace, AgentTurn, ToolExecution


@dataclass(slots=True)
class _ToolCallBuffer:
    id: str = ""
    name: str = ""
    arguments: str = ""


class AgentLoop:
    """Stream model turns until one finishes without requesting a tool."""

    def __init__(
        self,
        *,
        model: ChatModel,
        model_name: str,
        tools: Sequence[Tool],
        max_tool_turns: int = 8,
    ) -> None:
        if max_tool_turns < 1:
            raise ValueError("max_tool_turns must be at least 1")

        self._model = model
        self._model_name = model_name
        self._tools = {tool.name: tool for tool in tools}
        self._max_tool_turns = max_tool_turns
        if len(self._tools) != len(tools):
            raise ValueError("Tool names must be unique")

    async def stream(
        self,
        messages: Sequence[ChatCompletionMessageParam],
        *,
        trace: AgentTrace | None = None,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Yield native chunks from every model turn in the trace."""
        event_stream = self.events(messages, trace=trace)
        try:
            async for event in event_stream:
                if event.type == "model_chunk" and event.chunk is not None:
                    yield event.chunk
        finally:
            await event_stream.aclose()

    async def events(
        self,
        messages: Sequence[ChatCompletionMessageParam],
        *,
        trace: AgentTrace | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Yield structured events for model, reasoning, and tool activity."""
        active_trace = trace or AgentTrace()
        if active_trace.status != "running" or active_trace.turns:
            raise ValueError("trace must be new and running")

        history = list(messages)
        active_turn: AgentTurn | None = None
        tool_turn_count = 0
        force_final = not self._tools

        try:
            yield AgentEvent(type="trace_start", trace=active_trace)
            while True:
                active_turn = active_trace.start_turn("model")
                yield AgentEvent(
                    type="turn_start",
                    trace=active_trace,
                    turn=active_turn,
                )

                tool_calls: dict[int, _ToolCallBuffer] = {}
                request = self._request(history, include_tools=not force_final)
                async for chunk in self._model.stream(request):
                    yield AgentEvent(
                        type="model_chunk",
                        trace=active_trace,
                        turn=active_turn,
                        chunk=chunk,
                    )
                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta
                    if delta.content:
                        active_turn.output_text += delta.content
                        yield AgentEvent(
                            type="text_delta",
                            trace=active_trace,
                            turn=active_turn,
                            chunk=chunk,
                            delta=delta.content,
                        )

                    thinking_delta = self._thinking_delta(delta.model_extra)
                    if thinking_delta:
                        active_turn.thinking_text += thinking_delta
                        yield AgentEvent(
                            type="thinking_delta",
                            trace=active_trace,
                            turn=active_turn,
                            chunk=chunk,
                            delta=thinking_delta,
                        )

                    for tool_call_delta in delta.tool_calls or []:
                        buffer = tool_calls.setdefault(
                            tool_call_delta.index,
                            _ToolCallBuffer(),
                        )
                        if tool_call_delta.id:
                            buffer.id += tool_call_delta.id
                        if tool_call_delta.function is not None:
                            if tool_call_delta.function.name:
                                buffer.name += tool_call_delta.function.name
                            if tool_call_delta.function.arguments:
                                buffer.arguments += tool_call_delta.function.arguments
                        yield AgentEvent(
                            type="tool_call_delta",
                            trace=active_trace,
                            turn=active_turn,
                            chunk=chunk,
                            delta=(
                                tool_call_delta.function.arguments
                                if tool_call_delta.function is not None
                                else None
                            ),
                            tool_call_index=tool_call_delta.index,
                        )

                    if choice.finish_reason is not None:
                        active_turn.finish_reason = choice.finish_reason

                assistant_message = self._assistant_message(
                    active_turn,
                    tool_calls,
                )
                active_turn.assistant_message = assistant_message

                if tool_calls:
                    if force_final:
                        raise ValueError("Model requested a tool when tools were disabled")
                    active_turn.kind = "tool"
                else:
                    active_turn.kind = "final"

                yield AgentEvent(
                    type="model_end",
                    trace=active_trace,
                    turn=active_turn,
                )

                if not tool_calls:
                    self._complete_turn(active_turn)
                    yield AgentEvent(
                        type="turn_end",
                        trace=active_trace,
                        turn=active_turn,
                    )
                    active_turn = None
                    active_trace.stop_reason = (
                        "max_tool_turns" if force_final and self._tools else "no_tool_calls"
                    )
                    active_trace.status = "completed"
                    active_trace.ended_at = datetime.now(UTC)
                    yield AgentEvent(type="trace_end", trace=active_trace)
                    return

                history.append(cast(ChatCompletionMessageParam, assistant_message))
                for index in sorted(tool_calls):
                    tool_call = tool_calls[index]
                    yield AgentEvent(
                        type="tool_start",
                        trace=active_trace,
                        turn=active_turn,
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        tool_title=(
                            self._tools[tool_call.name].title
                            if tool_call.name in self._tools
                            else None
                        ),
                        tool_arguments=tool_call.arguments,
                    )
                    execution = await self._execute_tool(
                        tool_call.id,
                        tool_call.name,
                        tool_call.arguments,
                    )
                    active_turn.tool_executions.append(execution)
                    yield AgentEvent(
                        type="tool_end",
                        trace=active_trace,
                        turn=active_turn,
                        tool_execution=execution,
                        tool_title=(
                            self._tools[execution.name].title
                            if execution.name in self._tools
                            else None
                        ),
                    )
                    history.append(
                        cast(
                            ChatCompletionMessageParam,
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": execution.result,
                            },
                        )
                    )

                self._complete_turn(active_turn)
                yield AgentEvent(
                    type="turn_end",
                    trace=active_trace,
                    turn=active_turn,
                )
                active_turn = None
                tool_turn_count += 1
                if tool_turn_count >= self._max_tool_turns:
                    force_final = True
        except BaseException as exc:
            status = (
                "cancelled"
                if isinstance(exc, (asyncio.CancelledError, GeneratorExit))
                else "failed"
            )
            if active_turn is not None:
                active_turn.status = status
                active_turn.error = str(exc) or type(exc).__name__
                active_turn.ended_at = datetime.now(UTC)
            active_trace.status = status
            active_trace.stop_reason = status
            active_trace.error = str(exc) or type(exc).__name__
            active_trace.ended_at = datetime.now(UTC)
            if isinstance(exc, Exception):
                yield AgentEvent(type="trace_end", trace=active_trace)
            raise
        finally:
            if active_trace.ended_at is None:
                active_trace.ended_at = datetime.now(UTC)

    def _request(
        self,
        history: Sequence[ChatCompletionMessageParam],
        *,
        include_tools: bool,
    ) -> CompletionCreateParamsBase:
        request: dict[str, Any] = {
            "model": self._model_name,
            "messages": list(history),
        }
        if include_tools:
            request["tools"] = [
                tool.as_chat_completion_tool()
                for tool in self._tools.values()
            ]
            request["tool_choice"] = "auto"
        return cast(CompletionCreateParamsBase, request)

    @staticmethod
    def _assistant_message(
        turn: AgentTurn,
        tool_calls: Mapping[int, _ToolCallBuffer],
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": "assistant",
            "content": turn.output_text or None,
        }
        if tool_calls:
            calls: list[dict[str, Any]] = []
            for index in sorted(tool_calls):
                tool_call = tool_calls[index]
                if not tool_call.id or not tool_call.name:
                    raise ValueError("Streamed tool call is missing id or name")
                calls.append(
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        },
                    }
                )
            message["tool_calls"] = calls
        return message

    @staticmethod
    def _thinking_delta(model_extra: Mapping[str, Any] | None) -> str | None:
        if not model_extra:
            return None
        for name in ("reasoning_content", "thinking", "reasoning"):
            value = model_extra.get(name)
            if isinstance(value, str) and value:
                return value
        return None

    async def _execute_tool(
        self,
        tool_call_id: str,
        name: str,
        arguments_json: str,
    ) -> ToolExecution:
        tool = self._tools.get(name)
        if tool is None:
            return self._tool_error(
                tool_call_id,
                name,
                arguments_json,
                f"Unknown tool: {name}",
            )

        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError:
            return self._tool_error(
                tool_call_id,
                name,
                arguments_json,
                "Tool arguments must be valid JSON",
            )
        if not isinstance(arguments, Mapping):
            return self._tool_error(
                tool_call_id,
                name,
                arguments_json,
                "Tool arguments must be a JSON object",
            )

        try:
            tool.validate_arguments(arguments)
        except ValueError as exc:
            return self._tool_error(
                tool_call_id,
                name,
                arguments_json,
                f"Tool arguments failed JSON Schema validation: {exc}",
            )

        try:
            result = tool.handler(arguments)
            if inspect.isawaitable(result):
                result = await result
            serialized_result, is_error = self._serialize_result(result)
            return ToolExecution(
                tool_call_id=tool_call_id,
                name=name,
                arguments=arguments_json,
                result=serialized_result,
                is_error=is_error,
            )
        except Exception as exc:
            return self._tool_error(
                tool_call_id,
                name,
                arguments_json,
                f"Tool execution failed: {exc}",
            )

    @staticmethod
    def _serialize_result(result: Any) -> tuple[str, bool]:
        if isinstance(result, str):
            return result, False
        try:
            return (
                json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                False,
            )
        except (TypeError, ValueError):
            return AgentLoop._error_result(
                "Tool result is not JSON serializable"
            ), True

    @staticmethod
    def _tool_error(
        tool_call_id: str,
        name: str,
        arguments: str,
        message: str,
    ) -> ToolExecution:
        return ToolExecution(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            result=AgentLoop._error_result(message),
            is_error=True,
        )

    @staticmethod
    def _error_result(message: str) -> str:
        return json.dumps(
            {"error": message},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _complete_turn(turn: AgentTurn) -> None:
        turn.status = "completed"
        turn.ended_at = datetime.now(UTC)
