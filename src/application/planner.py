"""Create an M1 Plan from a Goal, existing context, and capability catalog."""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import Any, cast
from uuid import uuid4

from openai.types.chat.completion_create_params import CompletionCreateParamsBase

from src.domain import (
    CapabilityResult,
    CapabilityStatus,
    Goal,
    GoalRef,
    Plan,
    PlanStatus,
    PlanStep,
)
from src.model import ChatModel

from .capability_catalog import CAPABILITY_CATALOG
from .execution_context import ExecutionContext
from .plan_validation import validate_plan, validate_replan


CapabilityCatalog = Mapping[str, Mapping[str, str]]
ExistingContext = Mapping[str, Sequence[str]]


_SYSTEM_PROMPT = """你是智慧经营系统的 Planner。

根据当前 Goal 和已有 Context，从 Capability Catalog 中选择完成当前请求所需的最少合理能力。

硬性规则：
1. Capability 没有固定执行顺序，可以跳过、重复和重新排列。
2. 如果已有 Context 已经满足某项后续能力的需要，不要重复执行无意义的前置能力。
3. 只能使用 Capability Catalog 中真实存在的 capability_id，不得创造新能力。
4. depends_on 只表达本 Plan 内真实必要的步骤依赖；无依赖时返回空数组。
5. step_id 在本 Plan 内必须唯一，使用简短、稳定、无顺序暗示的英文标识。
6. 只输出 JSON 对象，不要输出解释或 Markdown。

输出格式：
{
  "steps": [
    {
      "step_id": "inspect_opportunities",
      "capability_id": "directional_insight",
      "depends_on": []
    }
  ]
}
"""


_REPLAN_SYSTEM_PROMPT = """你正在调整一个已经开始执行的智慧经营 Plan。

根据当前 Goal、当前 Plan、已有 Context、各步骤执行结果、最近一次 NO_RESULT 和 Capability Catalog，生成完整的 Plan 新版本，回答接下来怎么办。

硬性规则：
1. 只能使用 Capability Catalog 中真实存在的 capability_id，不得创造新能力。
2. 已经 SUCCESS 或 PARTIAL_SUCCESS 且仍然有效的步骤可以保留，但不得重复执行，也不得改变其 step_id 对应的 capability_id。
3. 最近的 NO_RESULT 表示能力正常执行但当前条件下没有业务结果；不要在新 Plan 中保留该旧 step_id，也不要让新步骤依赖它。
4. 可以再次调用同一 capability_id，但必须使用新的 step_id，并结合当前 Context 调整后续路径。
5. Capability 可以跳过、重复和重新排列；不要机械补齐全部能力。
6. 只加入完成当前 Goal 所需的最少步骤。
7. depends_on 只表达新 Plan 内真实必要的依赖；step_id 在新 Plan 内必须唯一。
8. 只输出 JSON 对象，不要输出解释或 Markdown。

输出格式：
{
  "steps": [
    {
      "step_id": "retained_or_new_step",
      "capability_id": "capability_from_catalog",
      "depends_on": []
    }
  ]
}
"""


class Planner:
    """Use a ChatModel to select the minimum reasonable capability plan."""

    def __init__(
        self,
        *,
        model: ChatModel,
        model_name: str,
        plan_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("Planner model_name is required")
        self._model = model
        self._model_name = model_name
        self._plan_id_factory = plan_id_factory or (
            lambda: f"plan_{uuid4().hex}"
        )

    async def plan(
        self,
        *,
        goal: Goal,
        context: ExistingContext | None = None,
        capability_catalog: CapabilityCatalog = CAPABILITY_CATALOG,
    ) -> Plan:
        if not capability_catalog:
            raise ValueError("Capability catalog must not be empty")

        request = self._model_request(
            goal=goal,
            context=context or {},
            capability_catalog=capability_catalog,
        )
        completion = await self._model.complete(request)
        content = self._completion_content(completion)

        try:
            payload = self._parse_payload(content)
        except ValueError:
            repair = await self._model.complete(self._repair_request(content))
            payload = self._parse_payload(self._completion_content(repair))

        steps = self._steps(payload)
        plan = Plan(
            plan_id=self._plan_id_factory(),
            version=1,
            goal_ref=GoalRef(goal.goal_id, goal.version),
            status=PlanStatus.ACTIVE,
            steps=steps,
        )
        validate_plan(plan, capability_catalog)
        return plan

    async def replan(
        self,
        *,
        context: ExecutionContext,
        last_result: CapabilityResult,
        capability_catalog: CapabilityCatalog = CAPABILITY_CATALOG,
    ) -> Plan:
        """Create the next full Plan version after a normal NO_RESULT outcome."""
        if last_result.status is not CapabilityStatus.NO_RESULT:
            raise ValueError("Planner.replan only supports NO_RESULT")
        if not capability_catalog:
            raise ValueError("Capability catalog must not be empty")

        old_plan = context.current_plan
        request = self._replan_model_request(
            context=context,
            last_result=last_result,
            capability_catalog=capability_catalog,
        )
        completion = await self._model.complete(request)
        content = self._completion_content(completion)

        try:
            payload = self._parse_payload(content)
        except ValueError:
            repair = await self._model.complete(self._repair_request(content))
            payload = self._parse_payload(self._completion_content(repair))

        new_plan = old_plan.revise(steps=self._steps(payload))
        validate_plan(new_plan, capability_catalog)
        validate_replan(old_plan, new_plan, context)
        return new_plan

    def _model_request(
        self,
        *,
        goal: Goal,
        context: ExistingContext,
        capability_catalog: CapabilityCatalog,
    ) -> CompletionCreateParamsBase:
        payload = {
            "goal": asdict(goal),
            "existing_context": {
                key: list(value)
                for key, value in context.items()
            },
            "capability_catalog": capability_catalog,
        }
        return cast(
            CompletionCreateParamsBase,
            {
                "model": self._model_name,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            payload,
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )

    def _replan_model_request(
        self,
        *,
        context: ExecutionContext,
        last_result: CapabilityResult,
        capability_catalog: CapabilityCatalog,
    ) -> CompletionCreateParamsBase:
        payload = {
            "goal": asdict(context.goal),
            "current_plan": asdict(context.current_plan),
            "known_context": context.known_context,
            "step_results": {
                step_id: asdict(result)
                for step_id, result in context.step_results.items()
            },
            "last_result": asdict(last_result),
            "capability_catalog": capability_catalog,
        }
        return cast(
            CompletionCreateParamsBase,
            {
                "model": self._model_name,
                "messages": [
                    {"role": "system", "content": _REPLAN_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            payload,
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )

    def _repair_request(self, invalid_content: str) -> CompletionCreateParamsBase:
        return cast(
            CompletionCreateParamsBase,
            {
                "model": self._model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "把输入修复为 Planner 所需的合法 JSON 对象。"
                            "只修复 JSON 格式，不增加、删除或改变步骤语义；"
                            "只输出 JSON，不要输出 Markdown。"
                        ),
                    },
                    {"role": "user", "content": invalid_content},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )

    @staticmethod
    def _completion_content(completion: Any) -> str:
        if not completion.choices:
            raise ValueError("Planner model returned no choices")
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("Planner model returned empty content")
        return content

    @staticmethod
    def _parse_payload(content: str) -> Mapping[str, Any]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("Planner model returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Planner model output must be a JSON object")
        return payload

    def _steps(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[PlanStep, ...]:
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("Planner model output requires at least one step")

        steps: list[PlanStep] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                raise ValueError("Planner step must be a JSON object")
            step_id = self._required_string(raw_step, "step_id")
            capability_id = self._required_string(raw_step, "capability_id")
            depends_on = self._string_list(raw_step.get("depends_on", []), "depends_on")
            steps.append(
                PlanStep(
                    step_id=step_id,
                    capability_id=capability_id,
                    depends_on=depends_on,
                )
            )
        return tuple(steps)

    @staticmethod
    def _required_string(payload: Mapping[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Planner step {field} is required")
        return value.strip()

    @staticmethod
    def _string_list(value: Any, field: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip()
            for item in value
        ):
            raise ValueError(f"Planner step {field} must be an array of strings")
        return tuple(item.strip() for item in value)
