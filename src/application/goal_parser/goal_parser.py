"""Goal Parser public service: model semantics plus deterministic safeguards."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from openai.types.chat.completion_create_params import CompletionCreateParamsBase

from src.domain import AudienceScope, ChannelAndActor, Constraint, Goal, Metric, MissingInformation, ProductOrNeedContext, Target, TimeHorizon
from src.model import ChatModel

_EDITABLE_FIELDS = ("goal_type", "metric", "target", "time_horizon", "audience_scope", "product_or_need_context", "constraints")
_SYSTEM_PROMPT = """你是智慧经营系统的 Goal Parser。只输出一个 JSON 对象，不要 Markdown。
只解释用户明确说过的内容，不能输出 actor、channel、goal_id、version 或授权结论。
修改已有 Goal 时，使用 updates：{"field":{"op":"KEEP"|"SET"|"CLEAR","value":...}}。
未修改字段用 KEEP；CLEAR 仅限用户明确要求删除整个字段。metric 应输出用户提及的名称，不得创造 code。
同时输出 needs_clarification(boolean) 和 clarification_question(string|null)。"""


class _ClarificationNeeded(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.missing = MissingInformation(field, reason, "无法安全应用本次 Goal 修改", True)
        super().__init__(reason)


class GoalParseStatus(StrEnum):
    READY = "READY"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    actor_ref: str | None = None
    channel_ref: str | None = None


@dataclass(frozen=True, slots=True)
class MetricVocabulary:
    """Small replaceable, versioned read-only metric vocabulary."""
    source_id: str
    version: str
    metrics: tuple[Mapping[str, Any], ...]

    @classmethod
    def bundled(cls) -> "MetricVocabulary":
        payload = json.loads(Path(__file__).with_name("metric_vocabulary.json").read_text(encoding="utf-8"))
        return cls(payload["source_id"], payload["version"], tuple(payload["metrics"]))

    def resolve(self, request_text: str) -> Metric | None:
        matches = [item for item in self.metrics if any(isinstance(alias, str) and alias in request_text for alias in item.get("aliases", ()))]
        if len(matches) != 1:
            return None
        return Metric(code=str(matches[0]["code"]), display_name=str(matches[0]["display_name"]))


@dataclass(frozen=True, slots=True)
class GoalParseResult:
    goal: Goal | None
    status: GoalParseStatus = GoalParseStatus.READY
    missing_information: tuple[MissingInformation, ...] = ()
    clarification_question: str | None = None
    error: str | None = None

    @property
    def need_clarification(self) -> bool:
        return self.status is GoalParseStatus.CLARIFICATION_REQUIRED

    @property
    def needs_clarification(self) -> bool:
        return self.need_clarification


class GoalParser:
    """The one public parsing entry point; identity and trust stay in Python."""
    def __init__(self, *, model: ChatModel, model_name: str, goal_id_factory: Callable[[], str] | None = None, metric_vocabulary: MetricVocabulary | None = None) -> None:
        if not model_name.strip():
            raise ValueError("GoalParser model_name is required")
        self._model, self._model_name = model, model_name
        self._goal_id_factory = goal_id_factory or (lambda: f"goal_{uuid4().hex}")
        self._metric_vocabulary = metric_vocabulary or MetricVocabulary.bundled()

    async def parse(self, *, user_request: str, runtime_context: RuntimeContext | None = None, existing_goal: Goal | None = None) -> GoalParseResult:
        request = user_request.strip()
        if not request:
            return self._failure("Goal request is required")
        try:
            payload = await self._completion_payload(request, existing_goal)
            goal, missing = self._build_goal(request, payload, runtime_context, existing_goal)
            if payload.get("needs_clarification") and not missing:
                missing = (MissingInformation("goal_details", "用户请求仍存在歧义", "需要确认后才能开始经营计划", True),)
            if any(item.required_before_execution for item in missing):
                return GoalParseResult(goal, GoalParseStatus.CLARIFICATION_REQUIRED, missing, self._question(payload, missing))
            return GoalParseResult(goal, GoalParseStatus.READY, missing, self._question(payload, missing))
        except _ClarificationNeeded as exc:
            return GoalParseResult(existing_goal, GoalParseStatus.CLARIFICATION_REQUIRED, (exc.missing,), self._question({}, (exc.missing,)))
        except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
            return self._failure("Goal parser protocol validation failed", existing_goal, str(exc))
        except Exception:
            return self._failure("Goal parser is temporarily unavailable", existing_goal)

    async def _completion_payload(self, request: str, existing: Goal | None) -> Mapping[str, Any]:
        first = await self._model.complete(self._model_request(request, existing))
        try:
            return self._decode(first.choices[0].message.content)
        except ValueError:
            repaired = await self._model.complete(self._repair_request(first.choices[0].message.content))
            return self._decode(repaired.choices[0].message.content)

    def _model_request(self, request: str, existing: Goal | None) -> CompletionCreateParamsBase:
        data: dict[str, Any] = {"user_request": request}
        if existing: data["current_goal"] = self._goal_summary(existing)
        return cast(CompletionCreateParamsBase, {"model": self._model_name, "messages": [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(data, ensure_ascii=False)}], "response_format": {"type": "json_object"}, "temperature": 0})

    def _repair_request(self, content: str | None) -> CompletionCreateParamsBase:
        return cast(CompletionCreateParamsBase, {"model": self._model_name, "messages": [{"role": "system", "content": "仅修复以下响应为合法 JSON 对象。不得添加、删除或改变任何业务字符串、数值、操作或 null 语义。"}, {"role": "user", "content": content or ""}], "response_format": {"type": "json_object"}, "temperature": 0})

    @staticmethod
    def _decode(content: str | None) -> Mapping[str, Any]:
        try: value = json.loads(content or "")
        except json.JSONDecodeError as exc: raise ValueError("invalid JSON") from exc
        if not isinstance(value, dict): raise ValueError("JSON response must be an object")
        if not isinstance(value.get("needs_clarification", False), bool): raise ValueError("needs_clarification must be a boolean")
        return value

    def _build_goal(self, request: str, payload: Mapping[str, Any], runtime: RuntimeContext | None, existing: Goal | None) -> tuple[Goal | None, tuple[MissingInformation, ...]]:
        values, changed = self._merged_values(request, payload, existing)
        goal_type = values["goal_type"]
        if not isinstance(goal_type, str) or not goal_type.strip():
            return None, (MissingInformation("goal_type", "无法可靠识别目标意图", "无法创建经营目标", True),)
        metric = self._metric(request, values["metric"], existing)
        missing: list[MissingInformation] = []
        if self._requires_metric(request, values["target"], metric):
            missing.append(MissingInformation("metric", "目标值未能唯一对应受治理指标", "不同指标会产生不同经营计划", True))
        data = dict(goal_type=goal_type, metric=metric, target=self._target(values["target"]), time_horizon=self._time_horizon(request, values["time_horizon"], existing), audience_scope=self._audience(request, values["audience_scope"], existing), product_or_need_context=self._product_context(request, values["product_or_need_context"], existing), constraints=self._constraints(request, values["constraints"], existing), channel_and_actor=self._trusted_context(runtime, existing), missing_information=tuple(missing))
        if existing:
            if not changed: raise ValueError("No supported Goal update was provided")
            return existing.revise(**data), tuple(missing)
        return Goal(self._goal_id_factory(), 1, request, **data), tuple(missing)

    def _merged_values(self, request: str, payload: Mapping[str, Any], existing: Goal | None) -> tuple[dict[str, Any], bool]:
        current, changed = self._goal_values(existing), False
        updates = payload.get("updates")
        if updates is not None and not isinstance(updates, Mapping): raise ValueError("updates must be an object")
        for field in _EDITABLE_FIELDS:
            instruction = updates.get(field) if isinstance(updates, Mapping) else None
            if instruction is None and field in payload: instruction = {"op": "SET", "value": payload[field]}
            if instruction is None and field == "product_or_need_context" and any(key in payload for key in ("product_mentions", "need_mentions", "product_or_need_raw_expression")):
                instruction = {"op": "SET", "value": {"product_mentions": payload.get("product_mentions", []), "need_mentions": payload.get("need_mentions", []), "product_or_need_raw_expression": payload.get("product_or_need_raw_expression")}}
            if instruction is None: continue
            if not isinstance(instruction, Mapping): raise ValueError(f"{field} update must be an object")
            op = instruction.get("op")
            if op == "KEEP": continue
            if op == "CLEAR":
                if not self._clear_is_explicit(request): raise _ClarificationNeeded(field, "未能从用户原文确认清空意图")
                current[field], changed = None, True
            elif op == "SET":
                if "value" not in instruction: raise ValueError(f"{field} SET requires value")
                current[field], changed = instruction["value"], True
            else: raise ValueError(f"{field} update op is invalid")
        return current, changed

    @staticmethod
    def _clear_is_explicit(request: str) -> bool:
        return any(token in request for token in ("取消", "清除", "删除", "不再", "移除", "不要"))

    def _metric(self, request: str, value: Any, existing: Goal | None) -> Metric | None:
        if value is None: return None
        item = self._object(value, "metric")
        resolved = self._metric_vocabulary.resolve(request)
        if resolved: return resolved
        if existing and existing.metric and item.get("code") == existing.metric.code:
            return existing.metric
        return None

    @staticmethod
    def _requires_metric(request: str, target: Any, metric: Metric | None) -> bool:
        return target is not None and metric is None and ("业绩" in request or "目标" in request)

    def _target(self, value: Any) -> Target | None:
        if value is None: return None
        item, raw = self._object(value, "target"), self._object(value, "target").get("value")
        if raw is None or isinstance(raw, bool): raise ValueError("target.value is required")
        try: parsed: Decimal | str = Decimal(str(raw))
        except InvalidOperation:
            if not isinstance(raw, str): raise ValueError("target.value is invalid")
            parsed = raw
        direction = item.get("direction", item.get("comparator", "at_least"))
        if direction not in {"at_least", "at_most", "equal_to", "improve"}: raise ValueError("target direction is invalid")
        return Target(parsed, self._string(item.get("unit")), cast(Any, direction))

    def _time_horizon(self, request: str, value: Any, existing: Goal | None) -> TimeHorizon | None:
        if value is None: return None
        raw = self._string(self._object(value, "time_horizon").get("raw_expression"))
        if existing and existing.time_horizon and raw == existing.time_horizon.raw_expression:
            return existing.time_horizon
        return TimeHorizon(raw_expression=raw) if raw and raw in request else None

    def _audience(self, request: str, value: Any, existing: Goal | None) -> AudienceScope | None:
        if value is None: return None
        item = self._object(value, "audience_scope"); raw, ref = self._string(item.get("raw_expression")), self._string(item.get("scope_reference"))
        if existing and existing.audience_scope and raw == existing.audience_scope.raw_expression and ref == existing.audience_scope.scope_reference:
            return existing.audience_scope
        if (raw and raw not in request) or (ref and ref not in request): return None
        scope_type = self._string(item.get("scope_type"))
        return AudienceScope(scope_type, ref, raw) if scope_type and (raw or ref) else None

    def _product_context(self, request: str, value: Any, existing: Goal | None) -> ProductOrNeedContext | None:
        if value is None: return None
        item = self._object(value, "product_or_need_context")
        old = existing.product_or_need_context if existing else None
        products = self._mentions(item.get("products", item.get("product_mentions", [])), request, old.products if old else ())
        needs = self._mentions(item.get("needs", item.get("need_mentions", [])), request, old.needs if old else ())
        raw = self._string(item.get("raw_expression", item.get("product_or_need_raw_expression")))
        if old and raw == old.raw_expression: raw = old.raw_expression
        else: raw = raw if raw and raw in request else None
        return ProductOrNeedContext(products, needs, raw) if products or needs or raw else None

    def _mentions(self, value: Any, request: str, old: tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(value, list): raise ValueError("mentions must be an array")
        return tuple(item for item in value if isinstance(item, str) and item.strip() and (item in request or item in old))

    def _constraints(self, request: str, value: Any, existing: Goal | None) -> tuple[Constraint, ...]:
        if value is None: return ()
        if not isinstance(value, list): raise ValueError("constraints must be an array")
        result = []
        for item in value:
            obj = self._object(item, "constraint"); description = self._required_string(obj.get("description"), "constraint description")
            if description in request or (existing and any(old.code == obj.get("code") and old.description == description for old in existing.constraints)):
                result.append(Constraint(self._required_string(obj.get("code"), "constraint code"), description, "user_request"))
        return tuple(result)

    @staticmethod
    def _trusted_context(runtime: RuntimeContext | None, existing: Goal | None) -> ChannelAndActor | None:
        if runtime is None and existing: return existing.channel_and_actor
        runtime = runtime or RuntimeContext()
        return ChannelAndActor(runtime.channel_ref, runtime.actor_ref, "runtime_context")
    @staticmethod
    def _goal_values(goal: Goal | None) -> dict[str, Any]:
        if goal is None: return {field: None for field in _EDITABLE_FIELDS}
        return {
            "goal_type": goal.goal_type,
            "metric": {"code": goal.metric.code, "display_name": goal.metric.display_name} if goal.metric else None,
            "target": {"value": goal.target.value, "unit": goal.target.unit, "direction": goal.target.comparator} if goal.target else None,
            "time_horizon": {"raw_expression": goal.time_horizon.raw_expression} if goal.time_horizon else None,
            "audience_scope": {"scope_type": goal.audience_scope.scope_type, "scope_reference": goal.audience_scope.scope_reference, "raw_expression": goal.audience_scope.raw_expression} if goal.audience_scope else None,
            "product_or_need_context": {"products": list(goal.product_or_need_context.products), "needs": list(goal.product_or_need_context.needs), "raw_expression": goal.product_or_need_context.raw_expression} if goal.product_or_need_context else None,
            "constraints": [{"code": item.code, "description": item.description} for item in goal.constraints],
        }
    @staticmethod
    def _object(value: Any, name: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping): raise ValueError(f"{name} must be an object")
        return value
    @staticmethod
    def _string(value: Any) -> str | None: return value.strip() if isinstance(value, str) and value.strip() else None
    def _required_string(self, value: Any, name: str) -> str:
        result = self._string(value)
        if result is None: raise ValueError(f"{name} is required")
        return result
    @staticmethod
    def _question(payload: Mapping[str, Any], missing: tuple[MissingInformation, ...]) -> str | None:
        candidate = payload.get("clarification_question")
        if isinstance(candidate, str) and candidate.strip(): return candidate.strip()
        return "请明确目标对应的具体经营指标。" if missing else None
    @staticmethod
    def _failure(message: str, goal: Goal | None = None, detail: str | None = None) -> GoalParseResult:
        return GoalParseResult(goal, GoalParseStatus.TECHNICAL_FAILURE, error=message if detail is None else f"{message}: {detail}")
    @staticmethod
    def _goal_summary(goal: Goal) -> Mapping[str, Any]:
        return {"goal_type": goal.goal_type, "metric": goal.metric.code if goal.metric else None, "target": str(goal.target.value) if goal.target else None, "version": goal.version}
