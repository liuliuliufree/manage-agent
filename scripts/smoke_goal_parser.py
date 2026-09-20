"""Run representative GoalParser scenarios against the configured real model."""

import asyncio
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletion
from openai.types.chat.completion_create_params import CompletionCreateParamsBase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.application import GoalParseResult, GoalParser, RuntimeContext  # noqa: E402
from src.model import ChatModelSettings, OpenAIChatModel  # noqa: E402


class RecordingChatModel:
    """Capture the real completion so the smoke output remains inspectable."""

    def __init__(self, delegate: OpenAIChatModel) -> None:
        self._delegate = delegate
        self.last_completion: ChatCompletion | None = None

    async def complete(
        self,
        request: CompletionCreateParamsBase,
    ) -> ChatCompletion:
        self.last_completion = await self._delegate.complete(request)
        return self.last_completion

    def stream(self, request: CompletionCreateParamsBase) -> Any:
        return self._delegate.stream(request)

    async def close(self) -> None:
        await self._delegate.close()


def print_case(
    *,
    title: str,
    user_question: str,
    llm_content: str | None,
    result: GoalParseResult | None,
) -> None:
    result_text = (
        json.dumps(
            asdict(result),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        if result is not None
        else "<GoalParser did not produce a result>"
    )
    print(
        f"\n=== {title} ===\n"
        f"User question:\n{user_question}\n"
        f"LLM JSON:\n{llm_content or '<empty>'}\n"
        f"Python processed JSON:\n{result_text}",
        flush=True,
    )


async def parse_case(
    *,
    parser: GoalParser,
    model: RecordingChatModel,
    title: str,
    user_question: str,
    runtime_context: RuntimeContext,
) -> GoalParseResult:
    model.last_completion = None
    result: GoalParseResult | None = None
    try:
        result = await parser.parse(
            user_request=user_question,
            runtime_context=runtime_context,
        )
        return result
    finally:
        llm_content = None
        if model.last_completion is not None:
            llm_content = model.last_completion.choices[0].message.content
        print_case(
            title=title,
            user_question=user_question,
            llm_content=llm_content,
            result=result,
        )


def verify_performance_goal(result: GoalParseResult) -> None:
    if result.need_clarification or result.goal is None:
        raise RuntimeError("Performance goal unexpectedly requires clarification")
    goal = result.goal
    if goal.metric is None or goal.metric.code.upper() != "NBEV":
        raise RuntimeError("Performance goal did not preserve the NBEV metric")
    if goal.target is None or goal.target.value != Decimal("500"):
        raise RuntimeError("Performance goal did not parse the 500 target")
    if goal.target.unit != "万元":
        raise RuntimeError("Performance goal did not normalize 500W to 万元")
    products = goal.product_or_need_context.products if goal.product_or_need_context else ()
    if set(products) != {"虚构产品A", "虚构产品B"}:
        raise RuntimeError("Performance goal did not preserve both product mentions")
    if goal.time_horizon is None or goal.time_horizon.raw_expression != "测试经营阶段":
        raise RuntimeError("Performance goal did not preserve the time expression")
    if goal.time_horizon.start_at is not None or goal.time_horizon.end_at is not None:
        raise RuntimeError("Model-generated activity dates entered the Goal")
    if goal.channel_and_actor is None or (
        goal.channel_and_actor.actor_id,
        goal.channel_and_actor.channel_id,
    ) != ("agent_001", "individual_insurance"):
        raise RuntimeError("Trusted runtime identity was not applied")


def verify_clarification(result: GoalParseResult) -> None:
    if not result.need_clarification or not result.clarification_question:
        raise RuntimeError("Ambiguous performance metric did not trigger clarification")


def verify_no_inferred_need(result: GoalParseResult) -> None:
    if result.need_clarification or result.goal is None:
        raise RuntimeError("Explicit opportunity request unexpectedly needs clarification")
    context = result.goal.product_or_need_context
    if context is not None and context.needs:
        raise RuntimeError("Age was incorrectly promoted to a customer need")


async def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")

    settings = ChatModelSettings.from_env()
    real_model = OpenAIChatModel(settings)
    model = RecordingChatModel(real_model)
    parser = GoalParser(model=model, model_name=settings.model)
    runtime_context = RuntimeContext(
        actor_ref="agent_001",
        channel_ref="individual_insurance",
    )

    try:
        performance = await parse_case(
            parser=parser,
            model=model,
            title="Performance goal",
            user_question="测试经营阶段完成500W NBEV，主推虚构产品A和虚构产品B。",
            runtime_context=runtime_context,
        )
        verify_performance_goal(performance)

        clarification = await parse_case(
            parser=parser,
            model=model,
            title="Ambiguous metric clarification",
            user_question="这个月测试业绩做到500W。",
            runtime_context=runtime_context,
        )
        verify_clarification(clarification)

        age_only = await parse_case(
            parser=parser,
            model=model,
            title="No inferred need from age",
            user_question="帮我看看50岁测试客户群有哪些经营机会。",
            runtime_context=runtime_context,
        )
        verify_no_inferred_need(age_only)
    finally:
        await model.close()

    print("\nGoalParser real-model smoke test passed.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
