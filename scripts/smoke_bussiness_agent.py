"""Run the BusinessAgent planning and fake-capability path against the real model."""

import asyncio
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletion
from openai.types.chat.completion_create_params import CompletionCreateParamsBase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.application import (  # noqa: E402
    CAPABILITY_CATALOG,
    BusinessAgent,
    BusinessAgentResponse,
    BusinessAgentStatus,
    CapabilityExecutor,
    GoalParser,
    Planner,
    RuntimeContext,
)
from src.domain import CapabilityRequest, CapabilityResult, CapabilityStatus  # noqa: E402
from src.model import ChatModelSettings, OpenAIChatModel  # noqa: E402


class RecordingChatModel:
    """Delegate to the real service while retaining inspectable completions."""

    def __init__(self, delegate: OpenAIChatModel) -> None:
        self._delegate = delegate
        self.completions: list[ChatCompletion] = []
        self.call_count = 0

    async def complete(
        self,
        request: CompletionCreateParamsBase,
    ) -> ChatCompletion:
        self.call_count += 1
        print(f"Calling real LLM #{self.call_count}...", flush=True)
        completion = await self._delegate.complete(request)
        self.completions.append(completion)
        print(f"Real LLM #{self.call_count} completed.", flush=True)
        return completion

    def stream(self, request: CompletionCreateParamsBase) -> Any:
        return self._delegate.stream(request)

    async def close(self) -> None:
        await self._delegate.close()


def successful_fake_capability(request: CapabilityRequest) -> CapabilityResult:
    return CapabilityResult(
        request_id=request.request_id,
        capability_id=request.capability_id,
        status=CapabilityStatus.SUCCESS,
    )


def print_case(
    *,
    title: str,
    user_request: str,
    existing_context: dict[str, list[str]],
    completions: list[ChatCompletion],
    response: BusinessAgentResponse,
) -> None:
    raw_outputs = [
        completion.choices[0].message.content
        for completion in completions
    ]
    print(
        f"\n=== {title} ===\n"
        f"User request:\n{user_request}\n"
        "Existing context:\n"
        f"{json.dumps(existing_context, ensure_ascii=False, indent=2)}\n"
        "LLM outputs (Goal Parser, then Planner when called):\n"
        f"{json.dumps(raw_outputs, ensure_ascii=False, indent=2)}\n"
        "BusinessAgent response:\n"
        f"{json.dumps(asdict(response), ensure_ascii=False, indent=2, default=str)}",
        flush=True,
    )


async def run_case(
    *,
    agent: BusinessAgent,
    model: RecordingChatModel,
    runtime_context: RuntimeContext,
    title: str,
    user_request: str,
    existing_context: dict[str, list[str]] | None,
    expected_status: BusinessAgentStatus,
    expected_capabilities: tuple[str, ...] = (),
    expected_model_calls: int,
) -> None:
    context = existing_context or {}
    completion_offset = len(model.completions)
    response = await agent.handle(
        user_request=user_request,
        runtime_context=runtime_context,
        existing_context=context,
    )
    case_completions = model.completions[completion_offset:]
    print_case(
        title=title,
        user_request=user_request,
        existing_context=context,
        completions=case_completions,
        response=response,
    )

    if response.status != expected_status:
        raise RuntimeError(
            f"{title} returned {response.status!r}; expected {expected_status!r}. "
            f"Error: {response.error or '<none>'}"
        )
    if len(case_completions) != expected_model_calls:
        raise RuntimeError(
            f"{title} made {len(case_completions)} model calls; "
            f"expected {expected_model_calls}"
        )
    if expected_status == BusinessAgentStatus.CLARIFICATION_REQUIRED:
        if not response.question or response.plan is not None:
            raise RuntimeError(
                f"{title} did not return a clarification-only response"
            )
        return

    if response.goal is None or response.plan is None:
        raise RuntimeError(f"{title} did not return both Goal and Plan")
    actual_capabilities = tuple(
        step.capability_id for step in response.plan.steps
    )
    if actual_capabilities != expected_capabilities:
        raise RuntimeError(
            f"{title} selected {actual_capabilities!r}; "
            f"expected {expected_capabilities!r}"
        )


async def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")

    settings = replace(
        ChatModelSettings.from_env(),
        timeout_seconds=30.0,
        max_retries=0,
    )
    real_model = OpenAIChatModel(settings)
    model = RecordingChatModel(real_model)
    agent = BusinessAgent(
        goal_parser=GoalParser(model=model, model_name=settings.model),
        planner=Planner(model=model, model_name=settings.model),
        capability_executor=CapabilityExecutor(
            {
                capability_id: successful_fake_capability
                for capability_id in CAPABILITY_CATALOG
            }
        ),
    )
    runtime_context = RuntimeContext(
        actor_ref="agent_smoke_001",
        channel_ref="individual_insurance",
    )

    try:
        await run_case(
            agent=agent,
            model=model,
            runtime_context=runtime_context,
            title="Opportunity only",
            user_request="测试场景最近有什么值得关注的经营机会？",
            existing_context=None,
            expected_status=BusinessAgentStatus.COMPLETED,
            expected_capabilities=("directional_insight",),
            expected_model_calls=2,
        )
        await run_case(
            agent=agent,
            model=model,
            runtime_context=runtime_context,
            title="Existing opportunity",
            user_request="围绕刚才的测试机会找一批候选客户。",
            existing_context={
                "opportunity_refs": ["opportunity_smoke_001"],
            },
            expected_status=BusinessAgentStatus.COMPLETED,
            expected_capabilities=("customer_targeting",),
            expected_model_calls=2,
        )
        await run_case(
            agent=agent,
            model=model,
            runtime_context=runtime_context,
            title="Ambiguous metric clarification",
            user_request="这个月测试业绩做到500W。",
            existing_context=None,
            expected_status=BusinessAgentStatus.CLARIFICATION_REQUIRED,
            expected_model_calls=1,
        )
    finally:
        await model.close()

    print("\nBusinessAgent real-model smoke test passed.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
