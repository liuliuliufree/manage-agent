"""FastAPI streaming boundary for the management agent."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent import AgentEvent
from model import ChatModel, ChatModelSettings, OpenAIChatModel

from .agent import ManageAgent
from .data_repository import BusinessDataRepository


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    data_source_id: str = Field(min_length=1)


def create_app(
    *,
    model: ChatModel | None = None,
    model_name: str | None = None,
    repository: BusinessDataRepository | None = None,
) -> FastAPI:
    app = FastAPI(title="Manage Agent API")
    data_repository = repository or BusinessDataRepository(Path("data/scenarios"))

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            owned_model: OpenAIChatModel | None = None
            terminal_sent = False
            try:
                active_model = model
                active_model_name = model_name
                if active_model is None:
                    settings = ChatModelSettings.from_env()
                    owned_model = OpenAIChatModel(settings)
                    active_model = owned_model
                    active_model_name = settings.model
                if not active_model_name:
                    raise RuntimeError("model_name is required with an injected model")

                agent = ManageAgent(
                    model=active_model,
                    model_name=active_model_name,
                    repository=data_repository,
                )
                run = agent.create_run(
                    user_message=request.message,
                    data_source_id=request.data_source_id,
                )
                async for event in run.events():
                    payload = _event_payload(event)
                    if payload is None:
                        continue
                    if payload["type"] in {"done", "error"}:
                        terminal_sent = True
                    yield _sse(payload)
            except Exception as exc:
                if not terminal_sent:
                    yield _sse({"type": "error", "message": str(exc)})
            finally:
                if owned_model is not None:
                    await owned_model.close()

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


def _event_payload(event: AgentEvent) -> dict[str, Any] | None:
    if event.type == "trace_start":
        return {
            "type": "trace",
            "trace_id": event.trace.id,
            "state": "running",
        }
    if event.type == "turn_start" and event.turn is not None:
        return {"type": "turn", "turn": event.turn.index, "state": "running"}
    if event.type == "tool_start":
        return {
            "type": "tool",
            "id": event.tool_call_id,
            "name": event.tool_name,
            "label": event.tool_title,
            "turn": event.turn.index if event.turn is not None else None,
            "state": "running",
            "arguments": _decode_json(event.tool_arguments),
        }
    if event.type == "tool_end" and event.tool_execution is not None:
        execution = event.tool_execution
        return {
            "type": "tool",
            "id": execution.tool_call_id,
            "name": execution.name,
            "label": event.tool_title,
            "turn": event.turn.index if event.turn is not None else None,
            "state": "error" if execution.is_error else "complete",
            "detail": "调用失败" if execution.is_error else "已返回结果",
            "result": _decode_json(execution.result),
        }
    if event.type == "text_delta" and event.delta:
        return {
            "type": "delta",
            "turn": event.turn.index if event.turn is not None else None,
            "delta": event.delta,
        }
    if event.type == "trace_end":
        if event.trace.status == "completed":
            return {
                "type": "done",
                "status": event.trace.status,
                "trace_id": event.trace.id,
                "turns": len(event.trace.turns),
            }
        return {
            "type": "error",
            "message": event.trace.error or "Agent run failed",
            "trace_id": event.trace.id,
        }
    return None


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _decode_json(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


app = create_app()
