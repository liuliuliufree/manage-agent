"""Translate a natural-language business request into the M1 Goal contract."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import uuid4

from openai.types.chat.completion_create_params import CompletionCreateParamsBase

from src.domain import (
    AudienceScope,
    ChannelAndActor,
    Constraint,
    Goal,
    Metric,
    ProductOrNeedContext,
    Target,
    TimeHorizon,
)
from src.model import ChatModel


_SYSTEM_PROMPT = """你是智慧经营系统的 Goal Parser，只负责理解用户明确表达的经营目标。

只输出一个 JSON 对象，不要输出解释或 Markdown。允许的字段如下：
- goal_type: string；无法判断时为 null。
- metric: {"code": string, "display_name": string|null} 或 null。
- target: {"target_type": string, "value": number|string, "unit": string|null,
  "direction": "at_least"|"at_most"|"equal_to"|"improve"} 或 null。
- time_horizon: {"raw_expression": string|null} 或 null。
- audience_scope: {"scope_type": string, "scope_reference": string|null,
  "raw_expression": string|null} 或 null。
- product_mentions: string[] 或 null。
- need_mentions: string[] 或 null。
- product_or_need_raw_expression: string 或 null。
- constraints: [{"code": string, "description": string}] 或 null。
- needs_clarification: boolean。
- clarification_question: string 或 null。

规则：
1. 只提取用户明确表达的业务语义；未表达的字段保持 null，不得补全或猜测。
2. 不得输出或决定 goal_id、version、original_request、actor、channel、authorization。
3. 时间表达只保留用户原文，不得推断活动起止日期。
4. 年龄、职业等客观描述不能自动推导为养老、保障等需求。
5. “业绩”“测试业绩”等泛化指标无法唯一确定时，needs_clarification=true，并提出一个简短问题；
   不得自行创造 test_performance、sales_performance 等指标代码来跳过澄清。
6. 如果提供了当前 Goal，用户未修改的字段可以省略；只表达本次明确的新增或修改。
7. goal_type 使用稳定的英文 snake_case：明确指标和数值目标使用
   performance_achievement；询问经营机会使用 opportunity_discovery；围绕已有机会找客户
   使用 customer_targeting；询问具体客户经营方式使用 strategy_advice；查看任务进展使用
   task_tracking。
8. 中文经营金额中的 500W、500万均规范为 value=500、unit="万元"。
9. “刚才的机会”“这个机会”等表达是在引用应用层已有 Context。只要用户动作明确，
   不得因为模型看不到该 Context 的具体内容而要求补充产品、需求或机会名称，也不得猜测其内容。
"""


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Trusted identity and channel context supplied by the application."""

    actor_ref: str | None = None
    channel_ref: str | None = None


@dataclass(frozen=True, slots=True)
class GoalParseResult:
    goal: Goal | None
    need_clarification: bool = False
    clarification_question: str | None = None

    @property
    def needs_clarification(self) -> bool:
        """Alias matching the model-output field name."""

        return self.need_clarification


class GoalParser:
    """Use a ChatModel for semantics and Python for trusted Goal fields."""

    def __init__(
        self,
        *,
        model: ChatModel,
        model_name: str,
        goal_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("GoalParser model_name is required")
        self._model = model
        self._model_name = model_name
        self._goal_id_factory = goal_id_factory or (
            lambda: f"goal_{uuid4().hex}"
        )

    async def parse(
        self,
        *,
        user_request: str,
        runtime_context: RuntimeContext | None = None,
        existing_goal: Goal | None = None,
    ) -> GoalParseResult:
        request_text = user_request.strip()
        if not request_text:
            raise ValueError("user_request is required")

        completion = await self._model.complete(
            self._model_request(request_text, existing_goal)
        )
        payload = self._parse_payload(completion.choices[0].message.content)

        need_clarification = self._required_bool(
            payload,
            "needs_clarification",
        )
        question = self._optional_string(payload.get("clarification_question"))
        if self._has_ambiguous_performance_metric(request_text, payload):
            need_clarification = True
            question = question or "这里的目标具体指NBEV、保费还是其他指标？"
        if need_clarification:
            if question is None:
                raise ValueError(
                    "Goal parser requested clarification without a question"
                )
            return GoalParseResult(
                goal=existing_goal,
                need_clarification=True,
                clarification_question=question,
            )

        context = runtime_context or RuntimeContext()
        goal = self._build_goal(
            request_text=request_text,
            payload=payload,
            runtime_context=context,
            existing_goal=existing_goal,
        )
        return GoalParseResult(goal=goal)

    @classmethod
    def _has_ambiguous_performance_metric(
        cls,
        request_text: str,
        payload: Mapping[str, Any],
    ) -> bool:
        """Prevent a model-invented metric code from resolving generic '业绩'."""

        if "业绩" not in request_text or payload.get("target") is None:
            return False
        metric = payload.get("metric")
        if metric is None:
            return True
        if not isinstance(metric, Mapping):
            return False
        display_name = cls._optional_string(metric.get("display_name"))
        if display_name is None:
            return True
        normalized = display_name.replace("测试", "").strip()
        return normalized == "业绩"

    def _model_request(
        self,
        user_request: str,
        existing_goal: Goal | None,
    ) -> CompletionCreateParamsBase:
        user_payload: dict[str, Any] = {"user_request": user_request}
        if existing_goal is not None:
            user_payload["current_goal"] = self._goal_summary(existing_goal)

        return cast(
            CompletionCreateParamsBase,
            {
                "model": self._model_name,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )

    def _build_goal(
        self,
        *,
        request_text: str,
        payload: Mapping[str, Any],
        runtime_context: RuntimeContext,
        existing_goal: Goal | None,
    ) -> Goal:
        goal_type = self._patched_string(payload, "goal_type", existing_goal, "goal_type")
        if goal_type is None:
            raise ValueError("Goal parser output requires goal_type")

        metric = self._metric(payload, existing_goal)
        target = self._target(payload, existing_goal)
        time_horizon = self._time_horizon(request_text, payload, existing_goal)
        audience_scope = self._audience_scope(request_text, payload, existing_goal)
        product_context = self._product_context(
            request_text,
            payload,
            existing_goal,
        )
        constraints = self._constraints(payload, existing_goal)
        channel_and_actor = ChannelAndActor(
            actor_id=runtime_context.actor_ref,
            channel_id=runtime_context.channel_ref,
            context_source="runtime_context",
        )

        changes = {
            "goal_type": goal_type,
            "metric": metric,
            "target": target,
            "time_horizon": time_horizon,
            "audience_scope": audience_scope,
            "product_or_need_context": product_context,
            "channel_and_actor": channel_and_actor,
            "constraints": constraints,
        }
        if existing_goal is not None:
            return existing_goal.revise(
                original_request=request_text,
                **changes,
            )

        return Goal(
            goal_id=self._goal_id_factory(),
            version=1,
            original_request=request_text,
            **changes,
        )

    @staticmethod
    def _parse_payload(content: str | None) -> Mapping[str, Any]:
        if not content:
            raise ValueError("Goal parser model returned empty content")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("Goal parser model returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Goal parser model output must be a JSON object")
        return payload

    @staticmethod
    def _required_bool(payload: Mapping[str, Any], field: str) -> bool:
        value = payload.get(field)
        if not isinstance(value, bool):
            raise ValueError(f"Goal parser output {field} must be a boolean")
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Goal parser output expected a string or null")
        stripped = value.strip()
        return stripped or None

    def _patched_string(
        self,
        payload: Mapping[str, Any],
        payload_field: str,
        existing_goal: Goal | None,
        goal_field: str,
    ) -> str | None:
        if payload_field in payload:
            return self._optional_string(payload[payload_field])
        if existing_goal is None:
            return None
        value = getattr(existing_goal, goal_field)
        return value if isinstance(value, str) else None

    def _metric(
        self,
        payload: Mapping[str, Any],
        existing_goal: Goal | None,
    ) -> Metric | None:
        if "metric" not in payload:
            return existing_goal.metric if existing_goal else None
        value = payload["metric"]
        if value is None:
            return None
        item = self._object(value, "metric")
        code = self._required_string(item, "code")
        return Metric(
            code=code,
            display_name=self._optional_string(item.get("display_name")),
        )

    def _target(
        self,
        payload: Mapping[str, Any],
        existing_goal: Goal | None,
    ) -> Target | None:
        if "target" not in payload:
            return existing_goal.target if existing_goal else None
        value = payload["target"]
        if value is None:
            return None
        item = self._object(value, "target")
        raw_value = item.get("value")
        target_type = self._optional_string(item.get("target_type"))
        if raw_value is None or isinstance(raw_value, bool):
            raise ValueError("Goal parser output target.value is required")
        if isinstance(raw_value, (int, float, Decimal)):
            parsed_value: Decimal | str = Decimal(str(raw_value))
        elif target_type in {None, "numeric", "number", "value"}:
            try:
                parsed_value = Decimal(str(raw_value))
            except InvalidOperation as exc:
                raise ValueError("Numeric target.value must be a number") from exc
        elif isinstance(raw_value, str):
            parsed_value = raw_value
        else:
            raise ValueError("Non-numeric target.value must be a string")

        direction = self._optional_string(item.get("direction")) or "at_least"
        if direction not in {"at_least", "at_most", "equal_to", "improve"}:
            raise ValueError("Goal parser output target.direction is invalid")
        return Target(
            value=parsed_value,
            unit=self._optional_string(item.get("unit")),
            comparator=cast(Any, direction),
        )

    def _time_horizon(
        self,
        request_text: str,
        payload: Mapping[str, Any],
        existing_goal: Goal | None,
    ) -> TimeHorizon | None:
        if "time_horizon" not in payload:
            return existing_goal.time_horizon if existing_goal else None
        value = payload["time_horizon"]
        if value is None:
            return None
        item = self._object(value, "time_horizon")
        raw_expression = self._verbatim_expression(
            item.get("raw_expression"),
            request_text,
        )
        if raw_expression is None:
            return None
        return TimeHorizon(
            raw_expression=raw_expression,
            start_at=None,
            end_at=None,
        )

    def _audience_scope(
        self,
        request_text: str,
        payload: Mapping[str, Any],
        existing_goal: Goal | None,
    ) -> AudienceScope | None:
        if "audience_scope" not in payload:
            return existing_goal.audience_scope if existing_goal else None
        value = payload["audience_scope"]
        if value is None:
            return None
        item = self._object(value, "audience_scope")
        raw_expression = self._verbatim_expression(
            item.get("raw_expression"),
            request_text,
        )
        scope_reference = self._verbatim_expression(
            item.get("scope_reference"),
            request_text,
        )
        return AudienceScope(
            scope_type=self._required_string(item, "scope_type"),
            scope_reference=scope_reference,
            raw_expression=raw_expression,
        )

    def _product_context(
        self,
        request_text: str,
        payload: Mapping[str, Any],
        existing_goal: Goal | None,
    ) -> ProductOrNeedContext | None:
        relevant_fields = {
            "product_mentions",
            "need_mentions",
            "product_or_need_raw_expression",
        }
        if relevant_fields.isdisjoint(payload):
            return existing_goal.product_or_need_context if existing_goal else None

        existing_context = (
            existing_goal.product_or_need_context
            if existing_goal is not None
            else None
        )
        products = (
            self._explicit_mentions(
                payload.get("product_mentions"),
                request_text,
                "product_mentions",
            )
            if "product_mentions" in payload
            else existing_context.products if existing_context else ()
        )
        needs = (
            self._explicit_mentions(
                payload.get("need_mentions"),
                request_text,
                "need_mentions",
            )
            if "need_mentions" in payload
            else existing_context.needs if existing_context else ()
        )
        raw_expression = (
            self._verbatim_expression(
                payload.get("product_or_need_raw_expression"),
                request_text,
            )
            if "product_or_need_raw_expression" in payload
            else None
        )
        mentions_changed = "product_mentions" in payload or "need_mentions" in payload
        if raw_expression is None and mentions_changed:
            raw_expression = self._mention_expression(
                request_text,
                tuple(
                    item
                    for item in products + needs
                    if item in request_text
                ),
            )
        if raw_expression is None and not mentions_changed and existing_context:
            raw_expression = existing_context.raw_expression
        if not products and not needs and raw_expression is None:
            return None
        return ProductOrNeedContext(
            products=products,
            needs=needs,
            raw_expression=raw_expression,
        )

    def _constraints(
        self,
        payload: Mapping[str, Any],
        existing_goal: Goal | None,
    ) -> tuple[Constraint, ...]:
        if "constraints" not in payload:
            return existing_goal.constraints if existing_goal else ()
        value = payload["constraints"]
        if value is None:
            return existing_goal.constraints if existing_goal else ()
        if not isinstance(value, list):
            raise ValueError("Goal parser output constraints must be an array or null")
        return tuple(
            Constraint(
                code=self._required_string(self._object(item, "constraint"), "code"),
                description=self._required_string(
                    self._object(item, "constraint"),
                    "description",
                ),
                source="user_request",
            )
            for item in value
        )

    def _explicit_mentions(
        self,
        value: Any,
        request_text: str,
        field: str,
    ) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list):
            raise ValueError(f"Goal parser output {field} must be an array or null")
        mentions: list[str] = []
        for item in value:
            mention = self._optional_string(item)
            if mention is not None and mention in request_text and mention not in mentions:
                mentions.append(mention)
        return tuple(mentions)

    def _verbatim_expression(self, value: Any, request_text: str) -> str | None:
        expression = self._optional_string(value)
        if expression is None or expression not in request_text:
            return None
        return expression

    @staticmethod
    def _mention_expression(
        request_text: str,
        mentions: tuple[str, ...],
    ) -> str | None:
        if not mentions:
            return None
        first_mention = min(request_text.index(item) for item in mentions)
        last_mention_end = max(
            request_text.index(item) + len(item)
            for item in mentions
        )
        clause_start = max(
            (request_text.rfind(marker, 0, first_mention) for marker in "，,；;。.!?！？"),
            default=-1,
        )
        expression = request_text[clause_start + 1:last_mention_end].strip()
        return expression or None

    @staticmethod
    def _object(value: Any, field: str) -> Mapping[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"Goal parser output {field} must be an object")
        return value

    def _required_string(self, payload: Mapping[str, Any], field: str) -> str:
        value = self._optional_string(payload.get(field))
        if value is None:
            raise ValueError(f"Goal parser output {field} is required")
        return value

    @staticmethod
    def _goal_summary(goal: Goal) -> Mapping[str, Any]:
        return {
            "goal_type": goal.goal_type,
            "metric": (
                {
                    "code": goal.metric.code,
                    "display_name": goal.metric.display_name,
                }
                if goal.metric
                else None
            ),
            "target": (
                {
                    "value": str(goal.target.value),
                    "unit": goal.target.unit,
                    "direction": goal.target.comparator,
                }
                if goal.target
                else None
            ),
            "time_horizon": (
                {"raw_expression": goal.time_horizon.raw_expression}
                if goal.time_horizon
                else None
            ),
            "audience_scope": (
                {
                    "scope_type": goal.audience_scope.scope_type,
                    "scope_reference": goal.audience_scope.scope_reference,
                    "raw_expression": goal.audience_scope.raw_expression,
                }
                if goal.audience_scope
                else None
            ),
            "product_mentions": (
                list(goal.product_or_need_context.products)
                if goal.product_or_need_context
                else []
            ),
            "need_mentions": (
                list(goal.product_or_need_context.needs)
                if goal.product_or_need_context
                else []
            ),
            "constraints": [
                {"code": item.code, "description": item.description}
                for item in goal.constraints
            ],
        }
