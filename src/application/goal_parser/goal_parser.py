"""Goal Parser Demo V1: one model extraction followed by deterministic checks."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from openai.types.chat.completion_create_params import CompletionCreateParamsBase

from src.domain import (
    AudienceScope,
    ChannelAndActor,
    Constraint,
    Goal,
    Metric,
    MissingInformation,
    ProductOrNeedContext,
    Target,
    TimeHorizon,
)
from src.model import ChatModel

from .prompts import SYSTEM_PROMPT


_FIELDS = frozenset(
    {
        "goal_type",
        "metric_text",
        "target_text",
        "time_text",
        "products",
        "needs",
        "audience_text",
        "constraints",
    }
)
_GOAL_TYPES = frozenset({"performance_achievement", "opportunity_discovery"})
_TEXT_FIELDS = ("metric_text", "target_text", "time_text", "audience_text")
_LIST_FIELDS = ("products", "needs", "constraints")
_AMOUNT_PATTERN = re.compile(
    r"^(?P<number>(?:\d+(?:\.\d+)?|\.\d+))\s*(?P<unit>元|万元|万|[Ww]|亿元|亿)?$"
)
_UNIT_MULTIPLIERS = {
    None: Decimal("1"),
    "元": Decimal("1"),
    "万": Decimal("10000"),
    "万元": Decimal("10000"),
    "W": Decimal("10000"),
    "w": Decimal("10000"),
    "亿": Decimal("100000000"),
    "亿元": Decimal("100000000"),
}


class GoalParseStatus(StrEnum):
    SUCCESS = "SUCCESS"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    actor_id: str
    channel_id: str
    context_source: str

    @property
    def is_valid(self) -> bool:
        return all(
            isinstance(value, str) and bool(value.strip())
            for value in (self.actor_id, self.channel_id, self.context_source)
        )


@dataclass(frozen=True, slots=True)
class GoalParseResult:
    status: GoalParseStatus
    goal: Goal | None = None
    missing_information: tuple[MissingInformation, ...] = ()
    clarification_question: str | None = None
    error: str | None = None
    diagnostics: dict[str, str] = field(default_factory=dict)

    @property
    def need_clarification(self) -> bool:
        return self.status is GoalParseStatus.CLARIFICATION_REQUIRED


class _MetricConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _MetricEntry:
    code: str
    display_name: str
    aliases: tuple[str, ...]
    unit: str


class MetricVocabulary:
    """Load and query the small versioned metric snapshot used by Demo V1."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        self._error: Exception | None = None
        self.source_id = ""
        self.version = ""
        self._entries: tuple[_MetricEntry, ...] = ()
        try:
            if data is not None and path is not None:
                raise _MetricConfigError("Metric configuration source is ambiguous")
            if data is None:
                source_path = Path(path) if path is not None else Path(__file__).with_name(
                    "metric_vocabulary.json"
                )
                loaded = json.loads(source_path.read_text(encoding="utf-8"))
            else:
                loaded = dict(data)
            self._load(loaded)
        except Exception as exc:  # surfaced later as a stable parse error
            self._error = exc

    def _load(self, payload: Any) -> None:
        if not isinstance(payload, dict) or set(payload) != {
            "source_id",
            "version",
            "metrics",
        }:
            raise _MetricConfigError("Metric configuration shape is invalid")
        source_id = payload["source_id"]
        version = payload["version"]
        metrics = payload["metrics"]
        if not isinstance(source_id, str) or not source_id.strip():
            raise _MetricConfigError("Metric source_id is required")
        if not isinstance(version, str) or not version.strip():
            raise _MetricConfigError("Metric version is required")
        if not isinstance(metrics, list) or not metrics:
            raise _MetricConfigError("Metric entries are required")

        entries: list[_MetricEntry] = []
        for item in metrics:
            if not isinstance(item, dict) or set(item) != {
                "code",
                "display_name",
                "aliases",
                "unit",
            }:
                raise _MetricConfigError("Metric entry shape is invalid")
            code = item["code"]
            display_name = item["display_name"]
            aliases = item["aliases"]
            unit = item["unit"]
            if not all(
                isinstance(value, str) and bool(value.strip())
                for value in (code, display_name, unit)
            ):
                raise _MetricConfigError("Metric text fields are required")
            if not isinstance(aliases, list) or not all(
                isinstance(alias, str) and alias.strip() for alias in aliases
            ):
                raise _MetricConfigError("Metric aliases are invalid")
            entries.append(
                _MetricEntry(
                    code=code.strip(),
                    display_name=display_name.strip(),
                    aliases=tuple(alias.strip() for alias in aliases),
                    unit=unit.strip(),
                )
            )
        self.source_id = source_id.strip()
        self.version = version.strip()
        self._entries = tuple(entries)

    def _ensure_valid(self) -> None:
        if self._error is not None:
            raise _MetricConfigError("Metric configuration is invalid") from self._error

    @property
    def prompt_terms(self) -> tuple[str, ...]:
        self._ensure_valid()
        terms: list[str] = []
        for entry in self._entries:
            terms.extend((entry.display_name, *entry.aliases))
        return tuple(dict.fromkeys(terms))

    def resolve(self, text: str) -> _MetricEntry | None:
        self._ensure_valid()
        normalized = text.strip().casefold()
        matches = {
            entry.code: entry
            for entry in self._entries
            if normalized
            in {entry.display_name.casefold(), *(alias.casefold() for alias in entry.aliases)}
        }
        return next(iter(matches.values())) if len(matches) == 1 else None

    @property
    def diagnostics(self) -> dict[str, str]:
        self._ensure_valid()
        return {
            "metric_vocabulary_source_id": self.source_id,
            "metric_vocabulary_version": self.version,
        }


class GoalParser:
    """Parse one complete request; revisions and recovery are intentionally absent."""

    def __init__(
        self,
        *,
        model: ChatModel,
        model_name: str,
        goal_id_factory: Callable[[], str] | None = None,
        metric_vocabulary: MetricVocabulary | None = None,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("Goal Parser model_name is required")
        self._model = model
        self._model_name = model_name
        self._goal_id_factory = goal_id_factory or (lambda: f"goal_{uuid4().hex}")
        self._metrics = metric_vocabulary or MetricVocabulary()

    async def parse(
        self,
        *,
        user_request: str,
        runtime_context: RuntimeContext | None = None,
        existing_goal: Goal | None = None,
    ) -> GoalParseResult:
        if runtime_context is None or not runtime_context.is_valid:
            return self._technical_failure("RUNTIME_CONTEXT_REQUIRED")
        if existing_goal is not None:
            return self._clarification(
                field="original_request",
                reason="首版不支持修改已有目标",
                impact="无法安全判断要修改的目标内容",
                question="请重新提交包含全部信息的完整目标。",
            )
        if not isinstance(user_request, str) or not user_request.strip():
            return self._clarification(
                field="goal_type",
                reason="未提供经营目标",
                impact="无法生成经营计划",
            )

        try:
            diagnostics = self._metrics.diagnostics
            terms = "、".join(self._metrics.prompt_terms)
        except _MetricConfigError:
            return self._technical_failure("METRIC_CONFIG_INVALID")

        try:
            completion = await self._model.complete(
                self._model_request(user_request=user_request, metric_terms=terms)
            )
        except Exception:
            return self._technical_failure("MODEL_CALL_FAILED", diagnostics)

        try:
            payload = self._payload(self._completion_content(completion))
        except (ValueError, TypeError, json.JSONDecodeError):
            return self._technical_failure("MODEL_PROTOCOL_INVALID", diagnostics)

        if not self._is_grounded(payload, user_request):
            return self._technical_failure("MODEL_GROUNDING_FAILED", diagnostics)

        goal_type = payload["goal_type"]
        if goal_type is None:
            return self._clarification(
                field="goal_type",
                reason="请求不是首版支持的单一完整经营目标",
                impact="无法生成经营计划",
                diagnostics=diagnostics,
            )

        metric_text = cast(str | None, payload["metric_text"])
        target_text = cast(str | None, payload["target_text"])
        metric_entry = self._metrics.resolve(metric_text) if metric_text else None
        metric = (
            Metric(code=metric_entry.code, display_name=metric_entry.display_name)
            if metric_entry is not None
            else None
        )
        target = self._target(
            target_text,
            metric_unit=metric_entry.unit if metric_entry is not None else None,
        )

        missing: list[MissingInformation] = []
        if goal_type == "performance_achievement" or metric_text is not None:
            if metric is None:
                missing.append(
                    self._missing(
                        "metric",
                        "指标未配置或存在歧义",
                        "无法确定目标的衡量口径",
                    )
                )
        if goal_type == "performance_achievement" or target_text is not None:
            if target is None:
                missing.append(
                    self._missing(
                        "target",
                        "目标值缺失或不符合首版支持的正向金额格式",
                        "无法确定量化目标",
                    )
                )

        products = tuple(cast(list[str], payload["products"]))
        needs = tuple(cast(list[str], payload["needs"]))
        missing_tuple = tuple(missing)
        goal = Goal(
            goal_id=self._goal_id_factory(),
            version=1,
            original_request=user_request,
            goal_type=goal_type,
            metric=metric,
            target=target,
            time_horizon=(
                TimeHorizon(raw_expression=cast(str, payload["time_text"]))
                if payload["time_text"] is not None
                else None
            ),
            audience_scope=(
                AudienceScope(
                    scope_type="user_expression",
                    raw_expression=cast(str, payload["audience_text"]),
                )
                if payload["audience_text"] is not None
                else None
            ),
            product_or_need_context=(
                ProductOrNeedContext(products=products, needs=needs)
                if products or needs
                else None
            ),
            channel_and_actor=ChannelAndActor(
                channel_id=runtime_context.channel_id.strip(),
                actor_id=runtime_context.actor_id.strip(),
                context_source=runtime_context.context_source.strip(),
            ),
            constraints=tuple(
                Constraint(
                    code="user_stated",
                    description=value,
                    source="user_request",
                )
                for value in cast(list[str], payload["constraints"])
            ),
            missing_information=missing_tuple,
        )

        if missing_tuple:
            return GoalParseResult(
                status=GoalParseStatus.CLARIFICATION_REQUIRED,
                goal=goal,
                missing_information=goal.missing_information,
                clarification_question="请补全缺失信息后重新提交完整目标。",
                diagnostics=diagnostics,
            )
        return GoalParseResult(
            status=GoalParseStatus.SUCCESS,
            goal=goal,
            missing_information=goal.missing_information,
            diagnostics=diagnostics,
        )

    def _model_request(
        self,
        *,
        user_request: str,
        metric_terms: str,
    ) -> CompletionCreateParamsBase:
        return cast(
            CompletionCreateParamsBase,
            {
                "model": self._model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT.replace(
                            "{metric_terms}", metric_terms
                        ),
                    },
                    {"role": "user", "content": user_request},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )

    @staticmethod
    def _completion_content(completion: Any) -> str:
        if not getattr(completion, "choices", None):
            raise ValueError("missing choice")
        content = completion.choices[0].message.content
        if not isinstance(content, str) or not content:
            raise ValueError("empty content")
        return content

    @staticmethod
    def _payload(content: str) -> dict[str, Any]:
        payload = json.loads(content)
        if not isinstance(payload, dict) or set(payload) != _FIELDS:
            raise ValueError("invalid payload fields")
        goal_type = payload["goal_type"]
        if goal_type is not None and goal_type not in _GOAL_TYPES:
            raise ValueError("invalid goal_type")
        for field_name in _TEXT_FIELDS:
            value = payload[field_name]
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"invalid {field_name}")
        for field_name in _LIST_FIELDS:
            value = payload[field_name]
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ValueError(f"invalid {field_name}")
        return payload

    @staticmethod
    def _is_grounded(payload: Mapping[str, Any], user_request: str) -> bool:
        values: list[str] = []
        for field_name in _TEXT_FIELDS:
            value = payload[field_name]
            if value is not None:
                values.append(value.strip())
        for field_name in _LIST_FIELDS:
            values.extend(item.strip() for item in payload[field_name])
        return all(value in user_request for value in values)

    @staticmethod
    def _target(text: str | None, *, metric_unit: str | None) -> Target | None:
        if text is None:
            return None
        match = _AMOUNT_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        unit = match.group("unit")
        if unit is None and metric_unit != "元":
            return None
        try:
            value = Decimal(match.group("number")) * _UNIT_MULTIPLIERS[unit]
        except (InvalidOperation, KeyError):
            return None
        if value <= 0:
            return None
        return Target(value=value, unit="元", comparator="at_least")

    @staticmethod
    def _missing(field_name: str, reason: str, impact: str) -> MissingInformation:
        return MissingInformation(
            field=field_name,
            reason=reason,
            impact=impact,
            required_before_execution=True,
        )

    def _clarification(
        self,
        *,
        field: str,
        reason: str,
        impact: str,
        question: str = "请补全缺失信息后重新提交完整目标。",
        diagnostics: dict[str, str] | None = None,
    ) -> GoalParseResult:
        missing = (self._missing(field, reason, impact),)
        return GoalParseResult(
            status=GoalParseStatus.CLARIFICATION_REQUIRED,
            missing_information=missing,
            clarification_question=question,
            diagnostics=dict(diagnostics or {}),
        )

    @staticmethod
    def _technical_failure(
        code: str,
        diagnostics: dict[str, str] | None = None,
    ) -> GoalParseResult:
        return GoalParseResult(
            status=GoalParseStatus.TECHNICAL_FAILURE,
            error=code,
            diagnostics=dict(diagnostics or {}),
        )
