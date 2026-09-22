"""Create one Demo V1 Plan from a Goal and the currently executable catalog."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import Any, cast
from uuid import uuid4

from openai.types.chat.completion_create_params import CompletionCreateParamsBase

from src.domain import Goal, GoalRef, Plan, PlanStatus, PlanStep
from src.model import ChatModel

from ..capability.capability_catalog import CAPABILITY_CATALOG
from .plan_validation import validate_plan


CapabilityCatalog = Mapping[str, Mapping[str, str]]
ExistingContext = Mapping[str, Sequence[str]]


_SYSTEM_PROMPT = """你是智慧经营系统的 Planner。

根据当前 Goal、已有引用 Context 和本次真正可执行的 Capability Catalog，选择完成请求所需的最少合理能力。

硬性规则：
1. Capability 没有固定顺序，可以跳过、重复和重排，不机械补齐全部能力。
2. 已有 Context 能满足后续能力时，不重复无意义的前置能力。
3. 只能使用 Catalog 中的 capability_id。
4. 后继需要本次运行的前序产物时，depends_on 必须直接包含生产该产物的步骤；系统不会自动搜索祖先步骤。
5. step_id 在本 Plan 内唯一；depends_on 只表达本 Plan 内真实依赖。
6. 无法用所给能力组织行动时，只返回 {"unable_to_plan": true}。
7. 其他情况只返回恰含 steps 的 JSON 对象，不输出解释或 Markdown：
{"steps":[{"step_id":"inspect","capability_id":"directional_insight","depends_on":[]}]}
"""


class PlanningUnavailableError(Exception):
    def __init__(self, code: str = "PLANNING_UNAVAILABLE", message: str | None = None):
        self.code = code
        self.message = message or (
            "当前可用能力无法形成处理此请求的计划，请调整请求或接入相应能力。"
        )
        super().__init__(self.message)


class PlannerError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class _StepProtocolError(ValueError):
    pass


class Planner:
    """Generate exactly one Plan; no execution-result-driven replanning exists."""

    def __init__(
        self,
        *,
        model: ChatModel,
        model_name: str,
        plan_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
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
        normalized_context = self._normalize_context(context)
        if not capability_catalog:
            raise PlanningUnavailableError()

        request = self._model_request(
            goal=goal,
            context=normalized_context,
            capability_catalog=capability_catalog,
        )
        try:
            completion = await self._model.complete(request)
        except Exception as exc:
            raise PlannerError(
                "PLANNER_MODEL_FAILED", "规划模型调用失败，请稍后重试。"
            ) from exc

        try:
            content = self._completion_content(completion)
            payload = self._decode(content)
        except json.JSONDecodeError:
            try:
                repair = await self._model.complete(self._repair_request(content))
                payload = self._decode(self._completion_content(repair))
            except json.JSONDecodeError as exc:
                raise PlannerError(
                    "PLANNER_PROTOCOL_INVALID", "规划结果格式无效。"
                ) from exc
            except PlannerError:
                raise
            except Exception as exc:
                raise PlannerError(
                    "PLANNER_MODEL_FAILED", "规划模型调用失败，请稍后重试。"
                ) from exc
        except PlannerError:
            raise
        except Exception as exc:
            raise PlannerError(
                "PLANNER_PROTOCOL_INVALID", "规划结果格式无效。"
            ) from exc

        try:
            branch, raw_steps = self._validate_payload(payload)
        except ValueError as exc:
            raise PlannerError(
                "PLANNER_PROTOCOL_INVALID", "规划结果格式无效。"
            ) from exc
        if branch == "unavailable":
            raise PlanningUnavailableError()

        try:
            steps = tuple(self._step(item) for item in raw_steps)
        except _StepProtocolError as exc:
            raise PlannerError(
                "PLANNER_PROTOCOL_INVALID", "规划结果格式无效。"
            ) from exc
        except ValueError as exc:
            raise PlannerError(
                "PLAN_INVALID", "规划结果未通过确定性校验。"
            ) from exc
        try:
            plan = Plan(
                plan_id=self._plan_id_factory(),
                version=1,
                goal_ref=GoalRef(goal.goal_id, goal.version),
                status=PlanStatus.ACTIVE,
                steps=steps,
            )
            validate_plan(plan, capability_catalog)
        except ValueError as exc:
            raise PlannerError("PLAN_INVALID", "规划结果未通过确定性校验。") from exc
        return plan

    @staticmethod
    def _normalize_context(
        context: ExistingContext | None,
    ) -> dict[str, tuple[str, ...]]:
        if context is None:
            return {}
        if not isinstance(context, Mapping):
            raise PlannerError("PLANNING_CONTEXT_INVALID", "规划上下文格式无效。")
        normalized: dict[str, tuple[str, ...]] = {}
        for key, values in context.items():
            if not isinstance(key, str) or not key.strip() or not key.endswith("_refs"):
                raise PlannerError("PLANNING_CONTEXT_INVALID", "规划上下文格式无效。")
            if not isinstance(values, (list, tuple)) or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                raise PlannerError("PLANNING_CONTEXT_INVALID", "规划上下文格式无效。")
            normalized[key] = tuple(value.strip() for value in values)
        return normalized

    def _model_request(
        self,
        *,
        goal: Goal,
        context: Mapping[str, Sequence[str]],
        capability_catalog: CapabilityCatalog,
    ) -> CompletionCreateParamsBase:
        payload = {
            "goal": asdict(goal),
            "existing_context": {key: list(values) for key, values in context.items()},
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
                        "content": json.dumps(payload, ensure_ascii=False, default=str),
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
                            "只修复输入的 JSON 语法，不补步骤、不改能力、不改变语义。"
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
        if not getattr(completion, "choices", None):
            raise PlannerError("PLANNER_PROTOCOL_INVALID", "规划结果格式无效。")
        content = completion.choices[0].message.content
        if not isinstance(content, str) or not content:
            raise PlannerError("PLANNER_PROTOCOL_INVALID", "规划结果格式无效。")
        return content

    @staticmethod
    def _decode(content: str) -> Any:
        return json.loads(content)

    @staticmethod
    def _validate_payload(payload: Any) -> tuple[str, list[dict[str, Any]]]:
        if not isinstance(payload, dict):
            raise ValueError("top level must be an object")
        if set(payload) == {"unable_to_plan"}:
            if payload["unable_to_plan"] is not True:
                raise ValueError("unable_to_plan must be true")
            return "unavailable", []
        if set(payload) != {"steps"}:
            raise ValueError("top level fields are invalid")
        steps = payload["steps"]
        if not isinstance(steps, list) or not steps:
            raise ValueError("steps must be a non-empty array")
        if not all(isinstance(item, dict) for item in steps):
            raise ValueError("each step must be an object")
        return "steps", cast(list[dict[str, Any]], steps)

    @staticmethod
    def _step(payload: Mapping[str, Any]) -> PlanStep:
        if set(payload) != {"step_id", "capability_id", "depends_on"}:
            raise _StepProtocolError("step fields are invalid")
        step_id = Planner._required_string(payload["step_id"])
        capability_id = Planner._required_string(payload["capability_id"])
        depends_on = payload["depends_on"]
        if not isinstance(depends_on, list) or not all(
            isinstance(item, str) and item.strip() for item in depends_on
        ):
            raise _StepProtocolError("depends_on must be an array of strings")
        return PlanStep(
            step_id=step_id,
            capability_id=capability_id,
            depends_on=tuple(item.strip() for item in depends_on),
        )

    @staticmethod
    def _required_string(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise _StepProtocolError("identifier is required")
        return value.strip()
