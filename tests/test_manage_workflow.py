"""Agent integration tests for the acts 1-3 management workflow."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionChunk


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manage import ActsOneToThreeAgent, ScenarioRepository  # noqa: E402
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


class ManageWorkflowTests(unittest.TestCase):
    def test_fake_model_completes_required_tool_path(self) -> None:
        scenario_arguments = '{"scenario_id":"demo-acts-1-3"}'
        model = FakeChatModel(
            chunk_streams=[
                [tool_chunk(1, "get_business_context", scenario_arguments)],
                [tool_chunk(2, "analyze_opportunities", scenario_arguments)],
                [
                    tool_chunk(
                        3,
                        "segment_opportunity_customers",
                        '{"scenario_id":"demo-acts-1-3","opportunity_id":"OPP-FAMILY-CI-GAP"}',
                    )
                ],
                [
                    tool_chunk(
                        4,
                        "explain_customer_decision",
                        '{"scenario_id":"demo-acts-1-3","opportunity_id":"OPP-FAMILY-CI-GAP","customer_id":"C001"}',
                    )
                ],
                [
                    chunk(
                        "turn-5",
                        delta={
                            "role": "assistant",
                            "content": (
                                "基于合成数据，推荐家庭责任变化与重疾保障缺口。"
                                "该机会包含 86 名机会客户、41 名可经营客户和 12 名高优先级客户。"
                            ),
                        },
                        finish_reason="stop",
                    )
                ],
            ]
        )
        agent = ActsOneToThreeAgent(
            model=model,
            model_name="fake-manage-model",
            repository=ScenarioRepository(ROOT / "data" / "scenarios"),
        )

        result = asyncio.run(
            agent.run(
                scenario_id="demo-acts-1-3",
                user_message="分析近期值得重点经营的加保机会。",
            )
        )

        self.assertFalse(result.degraded)
        self.assertEqual(result.segment_result["funnel"]["priority_customers"], 12)
        self.assertEqual(result.customer_decisions[0]["customer_id"], "C001")
        self.assertIn("合成数据", result.answer)
        self.assertEqual(len(model.requests), 5)

    def test_ungrounded_final_answer_is_replaced_by_template(self) -> None:
        analysis = {
            "recommended_opportunity_id": "OPP-FAMILY-CI-GAP",
            "opportunities": [
                {
                    "opportunity_id": "OPP-FAMILY-CI-GAP",
                    "name": "家庭责任变化与重疾保障缺口",
                }
            ],
        }
        segment = {
            "funnel": {
                "opportunity_customers": 86,
                "eligible_customers": 41,
                "priority_customers": 12,
            }
        }

        self.assertFalse(
            ActsOneToThreeAgent._answer_is_grounded(
                "基于合成数据，共有 99 名机会客户、41 名可经营客户和 12 名高优先级客户。",
                analysis,
                segment,
            )
        )

    def test_missing_tool_calls_falls_back_to_deterministic_result(self) -> None:
        model = FakeChatModel(
            chunk_streams=[
                [
                    chunk(
                        "turn-1",
                        delta={"role": "assistant", "content": "直接回答。"},
                        finish_reason="stop",
                    )
                ]
            ]
        )
        agent = ActsOneToThreeAgent(
            model=model,
            model_name="fake-manage-model",
            repository=ScenarioRepository(ROOT / "data" / "scenarios"),
        )

        result = asyncio.run(
            agent.run(
                scenario_id="demo-acts-1-3",
                user_message="分析近期机会。",
            )
        )

        self.assertTrue(result.degraded)
        self.assertIn("Agent 未形成必需产物", result.degradation_reason or "")
        self.assertEqual(result.segment_result["funnel"]["priority_customers"], 12)
        self.assertIn("确定性模板", result.answer)


if __name__ == "__main__":
    unittest.main()
