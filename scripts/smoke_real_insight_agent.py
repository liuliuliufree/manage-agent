r"""Real-model smoke for the current M4 directional-insight story.

This is an evaluation harness, not a production Capability or Agent entry
point.  The model must use the three read-only tools to inspect one registered
product document and calculate observations from the actual snapshot, then
explain one defensible business direction without inventing a recommendation,
customer list, or NBEV forecast.

Run from the repository root after configuring BASE_URL, API_KEY and MODEL in
the environment or in .env:

    $env:PYTHONPATH = "src"
    .\.venv\Scripts\python.exe scripts\smoke_real_insight_agent.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from agent import AgentLoop, AgentTrace  # noqa: E402
from model import ChatModelSettings, OpenAIChatModel  # noqa: E402
from src.application.insight_tools import (  # noqa: E402
    InsightToolConfig,
    build_insight_tools,
)


AS_OF = "2026-09-22T00:00:00+08:00"
WINDOW = {
    "start": "2026-06-24T00:00:00+08:00",
    "end": AS_OF,
}
SYSTEM_PROMPT = f"""
你是平安寿险一线代理人的“智慧经营智能体”洞察步骤评测对象。
本次只评测一次性的 M4 定向洞察故事，不执行圈客、策略生成、任务创建或 Replan。

用户请求：当前处于开门红阶段，目标500W NBEV，主推“御享分红26”和“御享金越年金”。
请围绕“是否存在一个有证据支持、值得进一步核实的经营问题”完成一次分析：

1. 必须先使用 search_knowledge 检索“御享金越年金”的已登记资料，关注领取条件/方式和限制；
2. 必须使用 read_knowledge 读取搜索结果给出的真实行号和 document_sha256，不得凭产品名或常识补写条款；
3. 必须使用 aggregate_records 统计以下真实快照：
   - customer_behaviors 在窗口 [{WINDOW["start"]}, {WINDOW["end"]}) 的 event_count 和 distinct_customers；
   - statement_kind=explicit_interest 的独立客户数，最好按 topic_code 分组；
   - 必要时补充 customer_profiles 的 age_band 分布。年龄、浏览和主题只能作为观察事实，不能直接推出适配或需求成立。
4. 最终给出一个“可进一步核实的经营问题/方向”，说明：与本次 Goal 的关系、实际统计证据、读取到的资料限制、数据覆盖限制和下一步核实事项。

硬约束：
- 只使用工具返回的事实；不要输出客户姓名、客户 ID、联系方式或入选名单；
- 不生成产品推荐、适合购买/投保结论、成交概率、客户评分或 NBEV 预测；
- 500W 只是用户目标背景，不能用它倒推客户数量或声称目标已完成；
- 不把 explicit_interest 改写成购买意愿，不把浏览或年龄改写成养老缺口；
- 明确这是 synthetic/demo snapshot，并保留数据时间窗和来源版本。

最终只输出简洁中文 Markdown，包含四个小标题：
“结论（待核实）”“证据”“限制”“下一步”。不要输出工具调用 JSON，不要编造工具没有返回的数字。
""".strip()

USER_PROMPT = (
    "请开始这次洞察评测。严格按系统要求调用工具，并在最后给出四段中文 Markdown。"
)


def _emit(event: str, **details: Any) -> None:
    print(
        json.dumps(
            {"event": event, **details},
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def _tool_executions(trace: AgentTrace) -> list[Any]:
    return [
        execution
        for turn in trace.turns
        for execution in turn.tool_executions
    ]


def _json_result(execution: Any) -> dict[str, Any]:
    try:
        value = json.loads(execution.result)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"{execution.name} returned non-JSON tool output"
        ) from exc
    if not isinstance(value, dict):
        raise AssertionError(f"{execution.name} returned a non-object result")
    return value


def _has_positive_business_claim(text: str) -> bool:
    """Reject positive claims while allowing the required limitation wording."""

    patterns = (
        r"(?:预计(?:将|可以|能|可)?(?:贡献)?|预测(?:将|可以|能|可)?(?:贡献)?|可贡献|能够贡献|贡献约)\s*[\d,.]+\s*(?:万|亿|元|W)?\s*NBEV",
        r"(?:适合|推荐)\s*(?:购买|投保|配置)",
        r"(?:保证|确定)\s*(?:收益|分红)",
        r"已完成\s*500\s*[万W]",
    )
    negative_markers = ("不能", "不应", "不建议", "不表示", "不等于", "尚不能", "避免")
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = text[max(0, match.start() - 10):match.start()]
            if not any(marker in prefix for marker in negative_markers):
                return True
    return False


def _assert_story(trace: AgentTrace) -> str:
    if trace.status != "completed":
        raise AssertionError(
            f"agent trace did not complete: status={trace.status}, "
            f"reason={trace.stop_reason}, error={trace.error}"
        )
    final_turn = trace.turns[-1] if trace.turns else None
    final_text = final_turn.output_text if final_turn is not None else ""
    if not final_text.strip():
        raise AssertionError("model returned no final story answer")

    executions = _tool_executions(trace)
    names = {execution.name for execution in executions}
    required = {"search_knowledge", "read_knowledge", "aggregate_records"}
    if not required.issubset(names):
        raise AssertionError(
            f"model did not complete the three-tool story: used={sorted(names)}"
        )
    failures = [execution for execution in executions if execution.is_error]
    if failures:
        raise AssertionError(
            "tool failures: "
            + "; ".join(f"{item.name}: {item.result}" for item in failures)
        )

    results = [_json_result(execution) for execution in executions]
    if not any(
        result.get("status") == "ok"
        and result.get("data", {}).get("total_matches", 0) > 0
        for result in results
        if isinstance(result.get("data"), dict)
    ):
        raise AssertionError("knowledge search did not return a matching source")
    if not any(
        result.get("status") == "ok"
        and isinstance(result.get("data", {}).get("text"), str)
        and result["data"]["text"].strip()
        for result in results
        if isinstance(result.get("data"), dict)
    ):
        raise AssertionError("model did not read a non-empty source excerpt")

    aggregate_results = [
        result for result in results
        if result.get("status") == "ok"
        and isinstance(result.get("data"), dict)
        and "matched_customers" in result["data"]
    ]
    if not aggregate_results:
        raise AssertionError("model did not produce a valid aggregate result")
    if not any(
        result["data"].get("totals", {}).get("event_count") == 105
        and result["data"].get("totals", {}).get("distinct_customers") == 40
        for result in aggregate_results
    ):
        raise AssertionError("model did not obtain the actual 90-day 105/40 baseline")
    if not any(
        result["data"].get("totals", {}).get("distinct_customers") == 15
        and any(
            item.get("field") == "statement_kind"
            and item.get("value") == "explicit_interest"
            for item in result["data"].get("normalized_query", {}).get("filters", [])
        )
        for result in aggregate_results
    ):
        raise AssertionError("model did not obtain the actual explicit-interest count")

    if _has_positive_business_claim(final_text):
        raise AssertionError("final answer contains a prohibited positive business claim")
    if not any(token in final_text for token in ("限制", "不能", "不等于", "待核实")):
        raise AssertionError("final answer does not state uncertainty or limitations")
    if not any(token in final_text for token in ("105", "40", "15")):
        raise AssertionError("final answer does not carry through actual tool-derived counts")
    return final_text


async def run(max_tool_turns: int) -> None:
    settings = ChatModelSettings.from_env(PROJECT_ROOT / ".env")
    model = OpenAIChatModel(settings)
    tools = build_insight_tools(InsightToolConfig.from_repository(PROJECT_ROOT))
    trace = AgentTrace()
    _emit("smoke_started", model=settings.model, tool_names=[tool.name for tool in tools])
    try:
        loop = AgentLoop(
            model=model,
            model_name=settings.model,
            tools=tools,
            max_tool_turns=max_tool_turns,
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ]
        async for event in loop.events(messages, trace=trace):
            if event.type == "tool_end" and event.tool_execution is not None:
                execution = event.tool_execution
                _emit(
                    "tool_completed",
                    name=execution.name,
                    arguments=execution.arguments,
                    is_error=execution.is_error,
                    result=execution.result,
                )
            elif event.type == "trace_end":
                _emit(
                    "trace_completed",
                    status=trace.status,
                    stop_reason=trace.stop_reason,
                    error=trace.error,
                )
        final_text = _assert_story(trace)
        _emit(
            "smoke_passed",
            tool_calls=[execution.name for execution in _tool_executions(trace)],
            final_answer=final_text,
        )
    finally:
        await model.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-tool-turns", type=int, default=8)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.max_tool_turns))
    except Exception as exc:
        _emit("smoke_failed", error=str(exc), error_type=type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
