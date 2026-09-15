"""End-to-end acts 1-3 Agent use case with deterministic fallback."""

from __future__ import annotations

import re
from typing import Any

from agent import AgentLoop, AgentTrace
from model import ChatModel

from .contracts import ActsAnalysisResult
from .prompts import SYSTEM_PROMPT, build_task_prompt
from .repository import ScenarioRepository
from .tools import ManageToolSession


class ActsOneToThreeAgent:
    """Run the business Agent while preserving authoritative artifacts."""

    def __init__(
        self,
        *,
        model: ChatModel,
        model_name: str,
        repository: ScenarioRepository,
        max_tool_turns: int = 8,
    ) -> None:
        self._model = model
        self._model_name = model_name
        self._repository = repository
        self._max_tool_turns = max_tool_turns

    async def run(
        self,
        *,
        scenario_id: str,
        user_message: str,
        selected_opportunity_id: str | None = None,
    ) -> ActsAnalysisResult:
        session = ManageToolSession(self._repository)
        trace = AgentTrace()
        loop = AgentLoop(
            model=self._model,
            model_name=self._model_name,
            tools=session.tools(),
            max_tool_turns=self._max_tool_turns,
        )
        failure_reason: str | None = None
        try:
            async for _ in loop.events(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_task_prompt(
                            scenario_id,
                            user_message,
                            selected_opportunity_id=selected_opportunity_id,
                        ),
                    },
                ],
                trace=trace,
            ):
                pass
        except Exception as exc:
            failure_reason = f"模型或 Agent 执行失败：{exc}"

        context = session.business_contexts.get(scenario_id)
        analysis = session.opportunity_analyses.get(scenario_id)
        expected_opportunity_id = selected_opportunity_id
        if analysis is not None and expected_opportunity_id is None:
            expected_opportunity_id = analysis["recommended_opportunity_id"]
        segment = (
            session.segment_results.get((scenario_id, expected_opportunity_id))
            if expected_opportunity_id
            else None
        )
        if context is None or analysis is None or segment is None:
            missing = []
            if context is None:
                missing.append("经营上下文")
            if analysis is None:
                missing.append("机会分析")
            if segment is None:
                missing.append("客群筛选")
            reason = f"Agent 未形成必需产物：{'、'.join(missing)}"
            failure_reason = f"{failure_reason}；{reason}" if failure_reason else reason
            context, analysis, segment = self._deterministic_artifacts(
                session,
                scenario_id,
                selected_opportunity_id=selected_opportunity_id,
            )
            expected_opportunity_id = segment["opportunity_id"]

        decisions = [
            value
            for (item_scenario, item_opportunity, _), value in sorted(
                session.customer_decisions.items()
            )
            if item_scenario == scenario_id
            and item_opportunity == expected_opportunity_id
        ]
        final_text = next(
            (
                turn.output_text
                for turn in reversed(trace.turns)
                if turn.kind == "final" and turn.output_text.strip()
            ),
            "",
        )
        if final_text and not self._answer_is_grounded(
            final_text, analysis, segment
        ):
            grounding_reason = "模型最终说明未完整保持推荐机会、漏斗或合成数据标识"
            failure_reason = (
                f"{failure_reason}；{grounding_reason}"
                if failure_reason
                else grounding_reason
            )
        if failure_reason or not final_text:
            if not failure_reason:
                failure_reason = "模型未返回最终说明"
            final_text = self._fallback_answer(context, analysis, segment)

        return ActsAnalysisResult(
            answer=final_text,
            business_context=context,
            opportunity_analysis=analysis,
            segment_result=segment,
            customer_decisions=decisions,
            degraded=failure_reason is not None,
            degradation_reason=failure_reason,
            trace=trace,
        )

    @staticmethod
    def _answer_is_grounded(
        answer: str,
        analysis: dict[str, Any],
        segment: dict[str, Any],
    ) -> bool:
        recommended = next(
            item
            for item in analysis["opportunities"]
            if item["opportunity_id"] == analysis["recommended_opportunity_id"]
        )
        if recommended["name"] not in answer or "合成" not in answer:
            return False
        expected = segment["funnel"]
        patterns = {
            "opportunity_customers": r"(\d+)\s*名?机会客户",
            "eligible_customers": r"(\d+)\s*名?可经营客户",
            "priority_customers": r"(\d+)\s*名?高优先级客户",
        }
        for key, pattern in patterns.items():
            matches = [int(value) for value in re.findall(pattern, answer)]
            if not matches or any(value != expected[key] for value in matches):
                return False
        return True

    @staticmethod
    def _deterministic_artifacts(
        session: ManageToolSession,
        scenario_id: str,
        *,
        selected_opportunity_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        service = session.service(scenario_id)
        context = service.get_business_context().to_dict()
        analysis = service.analyze_opportunities().to_dict()
        opportunity_id = (
            selected_opportunity_id or analysis["recommended_opportunity_id"]
        )
        segment = service.segment_opportunity_customers(opportunity_id).to_dict()
        session.business_contexts[scenario_id] = context
        session.opportunity_analyses[scenario_id] = analysis
        session.segment_results[(scenario_id, opportunity_id)] = segment
        return context, analysis, segment

    @staticmethod
    def _fallback_answer(
        context: dict[str, Any],
        analysis: dict[str, Any],
        segment: dict[str, Any],
    ) -> str:
        request = context["request"]
        opportunities = analysis["opportunities"]
        recommended = next(
            item
            for item in opportunities
            if item["opportunity_id"] == analysis["recommended_opportunity_id"]
        )
        comparisons = "；".join(
            f"{item['name']} {item['customer_count']} 人（综合分 {item['composite_score']:.2f}）"
            for item in opportunities
        )
        funnel = segment["funnel"]
        exclusions = "、".join(
            f"{reason} {count} 人"
            for reason, count in segment["exclusion_counts"].items()
        )
        priority_ids = "、".join(
            item["customer_id"] for item in segment["priority_customers"]
        )
        boundary_text = "；".join(
            item["text"] for item in request["boundaries"]
        )
        return (
            f"本次目标是：{request['goal_text']}\n\n"
            f"不可放宽的边界：{boundary_text}\n\n"
            f"机会比较：{comparisons}。推荐“{recommended['name']}”，依据为当前合成快照的透明规则综合分。\n\n"
            f"选中机会漏斗：{funnel['opportunity_customers']} 名机会客户 → "
            f"{funnel['eligible_customers']} 名可经营客户 → "
            f"{funnel['priority_customers']} 名高优先级客户。主要排除为：{exclusions}。\n\n"
            f"高优先级客户：{priority_ids}。这些客户仅表示当前可开展保障检视，具体产品适当性和销售沟通仍需具备资格的专业人员确认。\n\n"
            "以上均为合成演示数据；预计响应、成本和综合分不是生产预测。当前说明由确定性模板生成。"
        )
