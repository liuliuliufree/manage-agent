"""Integration tests for the autonomous management agent."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionChunk
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manage import BusinessDataRepository, ManageAgent  # noqa: E402
from manage.api import _event_payload, create_app  # noqa: E402
from model import FakeChatModel  # noqa: E402


def chunk(
    chunk_id: str,
    *,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "fake-manage-model",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
    )


def tool_chunk(index: int, name: str, arguments: str) -> ChatCompletionChunk:
    return chunk(
        f"turn-{index}",
        delta={
            "role": "assistant",
            "tool_calls": [
                {
                    "index": 0,
                    "id": f"call-{index}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        },
        finish_reason="tool_calls",
    )


class ManageAgentTests(unittest.TestCase):
    def create_agent(self, model: FakeChatModel) -> ManageAgent:
        return ManageAgent(
            model=model,
            model_name="fake-manage-model",
            repository=BusinessDataRepository(ROOT / "data" / "scenarios"),
        )

    def test_model_can_choose_a_tool_without_a_fixed_call_path(self) -> None:
        model = FakeChatModel(
            chunk_streams=[
                [
                    tool_chunk(
                        1,
                        "segment_opportunity_customers",
                        '{"data_source_id":"demo-acts-1-3","opportunity_id":"OPP-FAMILY-CI-GAP"}',
                    )
                ],
                [
                    chunk(
                        "turn-2",
                        delta={
                            "role": "assistant",
                            "content": "筛选已完成，共有 12 名高优先级客户。",
                        },
                        finish_reason="stop",
                    )
                ],
            ]
        )

        result = asyncio.run(
            self.create_agent(model).run(
                data_source_id="demo-acts-1-3",
                user_message="直接筛选家庭责任机会客户。",
            )
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.trace.turns), 2)
        self.assertEqual(
            [item["tool_name"] for item in result.artifacts],
            ["segment_opportunity_customers"],
        )
        self.assertIn("12 名", result.answer)
        request_tools = {
            item["function"]["name"] for item in model.requests[0]["tools"]
        }
        self.assertEqual(
            request_tools,
            {
                "get_business_context",
                "analyze_opportunities",
                "segment_opportunity_customers",
                "explain_customer_decision",
            },
        )

    def test_agent_may_answer_without_calling_a_tool(self) -> None:
        model = FakeChatModel(
            chunk_streams=[
                [
                    chunk(
                        "turn-1",
                        delta={"role": "assistant", "content": "请补充希望分析的目标。"},
                        finish_reason="stop",
                    )
                ]
            ]
        )

        result = asyncio.run(
            self.create_agent(model).run(
                data_source_id="demo-acts-1-3",
                user_message="你好",
            )
        )

        self.assertEqual(result.answer, "请补充希望分析的目标。")
        self.assertEqual(result.artifacts, [])
        self.assertEqual(result.stop_reason, "no_tool_calls")

    def test_stream_events_expose_trace_turn_and_tool_lifecycle(self) -> None:
        model = FakeChatModel(
            chunk_streams=[
                [
                    tool_chunk(
                        1,
                        "get_business_context",
                        '{"data_source_id":"demo-acts-1-3"}',
                    )
                ],
                [chunk("turn-2", delta={"content": "完成。"}, finish_reason="stop")],
            ]
        )
        run = self.create_agent(model).create_run(
            data_source_id="demo-acts-1-3",
            user_message="读取当前经营背景。",
        )

        async def collect() -> list[dict[str, Any]]:
            values = []
            async for event in run.events():
                payload = _event_payload(event)
                if payload is not None:
                    values.append(payload)
            return values

        payloads = asyncio.run(collect())
        self.assertEqual(payloads[0]["type"], "trace")
        self.assertTrue(any(item["type"] == "turn" for item in payloads))
        tool_events = [item for item in payloads if item["type"] == "tool"]
        self.assertEqual([item["state"] for item in tool_events], ["running", "complete"])
        self.assertEqual(tool_events[0]["label"], "理解目标与边界")
        self.assertEqual(
            tool_events[0]["arguments"],
            {"data_source_id": "demo-acts-1-3"},
        )
        self.assertEqual(
            tool_events[1]["result"]["metadata"]["data_source_id"],
            "demo-acts-1-3",
        )
        deltas = [item for item in payloads if item["type"] == "delta"]
        self.assertEqual(deltas[0]["turn"], 2)
        self.assertEqual(payloads[-1]["type"], "done")

    def test_http_endpoint_streams_the_real_agent_event_contract(self) -> None:
        model = FakeChatModel(
            chunk_streams=[
                [chunk("turn-1", delta={"content": "接口已连接。"}, finish_reason="stop")]
            ]
        )
        app = create_app(
            model=model,
            model_name="fake-manage-model",
            repository=BusinessDataRepository(ROOT / "data" / "scenarios"),
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/chat/stream",
                json={
                    "message": "检查连接",
                    "data_source_id": "demo-acts-1-3",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type":"trace"', response.text)
        self.assertIn('"type":"delta","turn":1,"delta":"接口已连接。"', response.text)
        self.assertIn('"type":"done"', response.text)


if __name__ == "__main__":
    unittest.main()
