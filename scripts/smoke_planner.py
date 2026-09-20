"""Run representative Planner scenarios against the configured real model."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletion
from openai.types.chat.completion_create_params import CompletionCreateParamsBase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.application import CAPABILITY_CATALOG, Planner  # noqa: E402
from src.domain import Goal, Plan  # noqa: E402
from src.model import ChatModelSettings, OpenAIChatModel  # noqa: E402


class RecordingChatModel:
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
    context: dict[str, list[str]],
    llm_content: str | None,
    plan: Plan | None,
) -> None:
    plan_text = (
        json.dumps(asdict(plan), ensure_ascii=False, indent=2, default=str)
        if plan is not None
        else "<Planner did not produce a Plan>"
    )
    print(
        f"\n=== {title} ===\n"
        f"Goal request:\n{user_question}\n"
        f"Existing context:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n"
        f"LLM JSON:\n{llm_content or '<empty>'}\n"
        f"Python Plan JSON:\n{plan_text}",
        flush=True,
    )


async def run_case(
    *,
    planner: Planner,
    model: RecordingChatModel,
    title: str,
    user_question: str,
    goal_type: str,
    context: dict[str, list[str]],
    expected_capabilities: tuple[str, ...],
) -> None:
    model.last_completion = None
    plan: Plan | None = None
    try:
        plan = await planner.plan(
            goal=Goal(
                goal_id=f"goal_smoke_{title.lower().replace(' ', '_')}",
                version=1,
                original_request=user_question,
                goal_type=goal_type,
            ),
            context=context,
            capability_catalog=CAPABILITY_CATALOG,
        )
    finally:
        llm_content = None
        if model.last_completion is not None:
            llm_content = model.last_completion.choices[0].message.content
        print_case(
            title=title,
            user_question=user_question,
            context=context,
            llm_content=llm_content,
            plan=plan,
        )

    actual = tuple(step.capability_id for step in plan.steps)
    if actual != expected_capabilities:
        raise RuntimeError(
            f"{title} selected {actual!r}; expected {expected_capabilities!r}"
        )


async def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")

    settings = ChatModelSettings.from_env()
    real_model = OpenAIChatModel(settings)
    model = RecordingChatModel(real_model)
    planner = Planner(model=model, model_name=settings.model)

    try:
        await run_case(
            planner=planner,
            model=model,
            title="Opportunity only",
            user_question="测试场景最近有什么值得关注的经营机会？",
            goal_type="opportunity_discovery",
            context={},
            expected_capabilities=("directional_insight",),
        )
        await run_case(
            planner=planner,
            model=model,
            title="Existing opportunity",
            user_question="围绕刚才的测试机会找一批候选客户。",
            goal_type="customer_targeting",
            context={"opportunity_refs": ["opportunity_test_001"]},
            expected_capabilities=("customer_targeting",),
        )
        await run_case(
            planner=planner,
            model=model,
            title="Existing customer",
            user_question="测试客户下一步应该怎么经营？",
            goal_type="strategy_advice",
            context={"customer_refs": ["customer_test_001"]},
            expected_capabilities=("strategy_generation",),
        )
        await run_case(
            planner=planner,
            model=model,
            title="Task tracking",
            user_question="看看上周测试经营任务进展怎么样。",
            goal_type="task_tracking",
            context={"task_refs": ["task_test_001"]},
            expected_capabilities=("tracking_iteration",),
        )
    finally:
        await model.close()

    print("\nPlanner real-model smoke test passed.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
