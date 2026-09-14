"""Exercise the AgentLoop tool-call cycle without network access."""

import asyncio
import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionChunk


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent import AgentEvent, AgentLoop, AgentTrace, Tool  # noqa: E402
from model import FakeChatModel  # noqa: E402


def chunk(
    chunk_id: str,
    *,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> ChatCompletionChunk:
    """Build one SDK-native chunk, matching the production model boundary."""
    return ChatCompletionChunk.model_validate(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "fake-agent-model",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
    )


def print_event(event: AgentEvent) -> str | None:
    """Print one observable AgentLoop event and return emitted answer text."""
    turn = event.turn
    if event.type == "trace_start":
        print(f"=== Trace {event.trace.id} started ===", flush=True)
    elif event.type == "turn_start" and turn is not None:
        print(f"\n[Turn {turn.index} start] kind={turn.kind}", flush=True)
    elif event.type == "model_end" and turn is not None:
        if turn.thinking_text:
            print(f"\n[Turn {turn.index} thinking_end]", flush=True)
        if turn.output_text:
            print()
        message = turn.assistant_message or {}
        tool_calls = message.get("tool_calls", [])
        tool_names = [
            call.get("function", {}).get("name")
            for call in tool_calls
            if isinstance(call, dict)
        ]
        print(
            f"[Turn {turn.index} model_end] "
            f"kind={turn.kind} finish_reason={turn.finish_reason} "
            f"tools={tool_names}",
            flush=True,
        )
        if not turn.thinking_text:
            print(
                f"[Turn {turn.index} thinking] unavailable "
                "(provider returned no reasoning field)",
                flush=True,
            )
    elif event.type == "tool_end" and event.tool_execution is not None:
        execution = event.tool_execution
        print(
            f"[Turn {turn.index if turn else '?'} tool_end] "
            f"name={execution.name} is_error={execution.is_error}\n"
            f"  arguments={execution.arguments}\n"
            f"  result={execution.result}",
            flush=True,
        )
    elif event.type == "thinking_delta" and event.delta:
        if turn is not None and turn.thinking_text == event.delta:
            print(f"[Turn {turn.index} thinking_start]", flush=True)
        print(event.delta, end="", flush=True)
    elif event.type == "text_delta" and event.delta:
        print(event.delta, end="", flush=True)
        return event.delta
    elif event.type == "turn_end" and turn is not None:
        if turn.kind == "final":
            print()
        print(
            f"[Turn {turn.index} end] status={turn.status} "
            f"finish_reason={turn.finish_reason}",
            flush=True,
        )
    elif event.type == "trace_end":
        print(
            f"[Trace end] status={event.trace.status} "
            f"stop_reason={event.trace.stop_reason}",
            flush=True,
        )
    return None


async def main() -> None:
    observed_arguments: list[dict[str, Any]] = []

    def lookup_customer(arguments: dict[str, Any]) -> dict[str, Any]:
        observed_arguments.append(arguments)
        return {"customer_id": arguments["customer_id"], "priority": "high"}

    tool = Tool(
        name="lookup_customer",
        description="Look up a customer summary.",
        parameters={
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
            "additionalProperties": False,
        },
        handler=lookup_customer,
    )
    model = FakeChatModel(
        chunk_streams=[
            [
                chunk(
                    "turn-1",
                    delta={
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "lookup_customer",
                                    "arguments": '{"customer_id":"C001"}',
                                },
                            }
                        ],
                    },
                    finish_reason="tool_calls",
                )
            ],
            [
                chunk("turn-2a", delta={"role": "assistant", "content": "C001 "}),
                chunk(
                    "turn-2b",
                    delta={"content": "is high priority."},
                    finish_reason="stop",
                ),
            ],
        ]
    )
    loop = AgentLoop(model=model, model_name="fake-agent-model", tools=[tool])
    trace = AgentTrace()
    event_types: list[str] = []
    answer_deltas: list[str] = []

    async for event in loop.events(
        [{"role": "user", "content": "Check customer C001."}],
        trace=trace,
    ):
        event_types.append(event.type)
        answer_delta = print_event(event)
        if answer_delta is not None:
            answer_deltas.append(answer_delta)

    assert observed_arguments == [{"customer_id": "C001"}]
    assert len(model.requests) == 2
    assert model.requests[1]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"customer_id":"C001","priority":"high"}',
    }
    assert trace.status == "completed"
    assert trace.stop_reason == "no_tool_calls"
    assert len(trace.turns) == 2
    assert trace.turns[0].kind == "tool"
    assert trace.turns[0].tool_executions[0].is_error is False
    assert trace.turns[1].kind == "final"
    assert trace.turns[1].output_text == "C001 is high priority."
    assert "".join(answer_deltas) == trace.turns[1].output_text
    assert event_types[0] == "trace_start"
    assert event_types[-1] == "trace_end"

    print("PASS: AgentLoop completed tool call -> tool result -> final answer")
    print(f"turns={len(trace.turns)} events={len(event_types)}")
    print(f"final={trace.turns[-1].output_text}")


if __name__ == "__main__":
    asyncio.run(main())
