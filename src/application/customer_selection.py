"""Evidence-grounded customer targeting for the synthetic Demo snapshot.

Facts are read by ``query_customer_evidence``.  Semantic customer/opportunity
judgements are produced by ``assess_customer_opportunity`` and remain labelled
as model inferences.  The capability handler validates references and tier
invariants before publishing a display result and the priority-only handoff.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.agent.tool import Tool
from src.domain import (
    CapabilityError,
    CapabilityOutput,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ErrorCategory,
)
from src.model import ChatModel

from .capability.artifact_flow import CapabilityIO
from .capability.artifact_store import ArtifactStore
from .insight_tools import InsightToolConfig, _Snapshot, _envelope, _error, _parse_time


_RELEVANCE = {"related", "unrelated", "uncertain"}
_NEED_STATES = {
    "explicit_self_need",
    "active_inquiry",
    "attention_only",
    "current_negative",
    "already_resolved",
    "other_person",
    "conflict",
    "insufficient",
}
_TIERS = {"priority", "further", "continued", None}
_EVIDENCE_ROLES = ("supporting_evidence", "limiting_evidence", "contradicting_evidence")
_TIER_FOR_STATE = {
    "explicit_self_need": "priority",
    "active_inquiry": "further",
    "attention_only": "continued",
}


class CustomerSelectionProtocolError(ValueError):
    """A model result or trusted reference failed publication validation."""


@dataclass(frozen=True, slots=True)
class CustomerSelectionConfig:
    insight: InsightToolConfig
    actor_id: str
    channel_id: str
    dataset_id: str = "insight_demo_v2"
    dataset_version: str = "2.0"
    tool_version: str = "customer-selection-tools-v1"
    prompt_version: str = "customer-opportunity-assessment-v1"

    def __post_init__(self) -> None:
        if not self.actor_id or not self.channel_id:
            raise ValueError("trusted actor_id and channel_id are required")


ArtifactResolver = Callable[[str], dict[str, Any]]


def _bound_snapshot(config: CustomerSelectionConfig) -> _Snapshot:
    snapshot = _Snapshot(config.insight)
    manifest = snapshot.manifest
    actual = (manifest.get("dataset_id"), manifest.get("version"))
    expected = (config.dataset_id, config.dataset_version)
    if actual != expected:
        raise ValueError(f"snapshot binding mismatch: {actual!r} != {expected!r}")
    if manifest.get("owner_actor_id") != config.actor_id or manifest.get("channel_id") != config.channel_id:
        raise PermissionError("snapshot is outside the trusted actor/channel scope")
    return snapshot


def _material_map(config: CustomerSelectionConfig) -> dict[str, dict[str, Any]]:
    document = json.loads((config.insight.client_root / "materials.json").read_text(encoding="utf-8"))
    return {item["material_id"]: item for item in document.get("materials", [])}


def _query_customer_evidence(config: CustomerSelectionConfig, arguments: Mapping[str, Any]) -> dict[str, Any]:
    try:
        snapshot = _bound_snapshot(config)
        requested = arguments.get("customer_ids")
        known = snapshot.customer_map()
        if requested is None:
            customer_ids = sorted(known)
        else:
            unknown = sorted(set(requested) - set(known))
            if unknown:
                return _error(config.insight, "RESOURCE_NOT_FOUND", f"unknown customer_id(s): {unknown}")
            customer_ids = list(dict.fromkeys(requested))
        materials = _material_map(config)
        start = _parse_time(snapshot.manifest["window_start"], "window_start")
        end = _parse_time(snapshot.manifest["window_end"], "window_end")
        grouped: dict[str, list[dict[str, Any]]] = {customer_id: [] for customer_id in customer_ids}
        for raw_event in snapshot.events:
            customer_id = raw_event["customer_id"]
            if customer_id not in grouped:
                continue
            event = dict(raw_event)
            material = materials.get(event.get("material_id"))
            event["material"] = None if material is None else {
                "material_id": material["material_id"],
                "kind": material["kind"],
                "title": material["title"],
                "topic_code": material["topic_code"],
            }
            grouped[customer_id].append(event)
        packages = []
        for customer_id in customer_ids:
            events = sorted(grouped[customer_id], key=lambda item: (item["occurred_at"], item["event_id"]))
            recent = [item for item in events if start <= _parse_time(item["occurred_at"], item["event_id"]) < end]
            history = [item for item in events if _parse_time(item["occurred_at"], item["event_id"]) < start]
            packages.append({
                "customer": dict(known[customer_id]),
                "recent_events": recent,
                "historical_events": history,
                "coverage": {
                    "window_start": snapshot.manifest["window_start"],
                    "window_end": snapshot.manifest["window_end"],
                    "window_semantics": "left_closed_right_open",
                    "recent_records_complete_for_authorized_snapshot": True,
                    "history_is_sparse": True,
                    "truncated": False,
                    "missing_statement_note": "浏览和活动没有客户原话；未发现反馈不表示现实中不存在反馈。",
                },
            })
        source = snapshot.source("customer_evidence")
        return _envelope(
            config.insight,
            "ok",
            {"customers": packages, "returned_customers": len(packages), "authorized_customers": len(known)},
            [source],
            warnings=["Synthetic authorized snapshot; sparse history is not a complete customer history."],
        )
    except PermissionError as exc:
        return _error(config.insight, "RESOURCE_FORBIDDEN", str(exc))
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _error(config.insight, "SOURCE_INVALID", str(exc))


def _model_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    """Remove source-side statement_kind so it cannot become a model shortcut."""
    result = {
        "customer": package["customer"],
        "coverage": package["coverage"],
        "recent_events": [],
        "historical_events": [],
    }
    for group in ("recent_events", "historical_events"):
        for event in package[group]:
            result[group].append({key: value for key, value in event.items() if key != "statement_kind"})
    return result


def _completion_content(completion: Any) -> str:
    choices = getattr(completion, "choices", None)
    if not choices:
        raise CustomerSelectionProtocolError("model returned no choice")
    content = getattr(choices[0].message, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise CustomerSelectionProtocolError("model returned empty content")
    return content


async def _assess_customer_opportunity(
    config: CustomerSelectionConfig,
    model: ChatModel,
    resolver: ArtifactResolver,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        opportunity = resolver(arguments["opportunity_ref"])
        packages = [resolver(ref) for ref in arguments["customer_evidence_refs"]]
        safe_packages = [_model_evidence(package) for package in packages]
        observed_at = arguments["observed_at"]
        system = (
            "你是客户机会证据评估模型。只能依据输入的原始记录判断，不得使用年龄或客户编号猜测需求，"
            "不得补造预算、保障缺口、资产、购买意愿、产品适配、成交概率或NBEV。"
            "逐客输出严格JSON。明确自身需求、主动了解、仅关注必须区分；替他人询问、同主题后续撤回、"
            "已解决、冲突或证据不足不得进入正向层级；无关主题否定不得机械覆盖当前机会。"
            "证据引用必须使用输入event_id，quote必须逐字存在于对应客户原话或素材标题。"
        )
        protocol = {
            "assessments": [{
                "customer_id": "string",
                "opportunity_relevance": "related|unrelated|uncertain",
                "need_state": "explicit_self_need|active_inquiry|attention_only|current_negative|already_resolved|other_person|conflict|insufficient",
                "supporting_evidence": [{"event_id": "string", "quote": "verbatim"}],
                "limiting_evidence": [{"event_id": "string", "quote": "verbatim"}],
                "contradicting_evidence": [{"event_id": "string", "quote": "verbatim"}],
                "need_summary": "string|null",
                "suggested_tier": "priority|further|continued|null",
                "reason": "string",
                "information_to_verify": ["string"],
            }]
        }
        completion = await model.complete({
            "model": getattr(model, "default_model", "configured-model"),
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({
                    "prompt_version": config.prompt_version,
                    "observed_at": observed_at,
                    "opportunity": opportunity,
                    "customer_evidence": safe_packages,
                    "output_protocol": protocol,
                }, ensure_ascii=False)},
            ],
        })
        raw = _completion_content(completion)
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or set(parsed) != {"assessments"} or not isinstance(parsed["assessments"], list):
            raise CustomerSelectionProtocolError("model output must contain only assessments array")
        return {
            "status": "ok",
            "data": {
                "assessments": parsed["assessments"],
                "inference_type": "model_inference",
                "audit": {
                    "model": getattr(model, "default_model", type(model).__name__),
                    "prompt_version": config.prompt_version,
                    "observed_at": observed_at,
                    "called_at": datetime.now(timezone.utc).isoformat(),
                    "completion_id": getattr(completion, "id", None),
                    "input_dataset": {"dataset_id": config.dataset_id, "version": config.dataset_version},
                    "result_status": "ok",
                },
            },
            "sources": [],
            "meta": {"tool_version": config.tool_version},
            "warnings": ["These categories are model inferences, not customer facts or deterministic rules."],
            "error": None,
        }
    except Exception as exc:
        code = "MODEL_PROTOCOL_INVALID" if isinstance(exc, (json.JSONDecodeError, CustomerSelectionProtocolError)) else "MODEL_CALL_FAILED"
        return {
            "status": "error", "data": None, "sources": [],
            "meta": {"tool_version": config.tool_version}, "warnings": [],
            "error": {"code": code, "message": str(exc)},
        }


def build_customer_selection_tools(
    config: CustomerSelectionConfig,
    *,
    model: ChatModel,
    artifact_resolver: ArtifactResolver,
) -> tuple[Tool, Tool]:
    query_schema = {
        "type": "object", "additionalProperties": False,
        "properties": {"customer_ids": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems": True}},
    }
    assess_schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "opportunity_ref": {"type": "string", "pattern": "^opportunity:[^:]+$"},
            "customer_evidence_refs": {"type": "array", "items": {"type": "string", "pattern": "^customer_evidence:[^:]+$"}, "minItems": 1, "maxItems": 50, "uniqueItems": True},
            "observed_at": {"type": "string", "format": "date-time"},
        },
        "required": ["opportunity_ref", "customer_evidence_refs", "observed_at"],
    }
    tools: dict[str, Tool] = {}

    def query_handler(args: Mapping[str, Any]) -> dict[str, Any]:
        try:
            tools["query_customer_evidence"].validate_arguments(args)
        except ValueError as exc:
            return _error(config.insight, "INVALID_ARGUMENT", str(exc))
        result = _query_customer_evidence(config, args)
        result["meta"]["tool_version"] = config.tool_version
        return result

    async def assess_handler(args: Mapping[str, Any]) -> dict[str, Any]:
        try:
            tools["assess_customer_opportunity"].validate_arguments(args)
        except ValueError as exc:
            return {"status": "error", "data": None, "sources": [], "meta": {"tool_version": config.tool_version}, "warnings": [], "error": {"code": "INVALID_ARGUMENT", "message": str(exc)}}
        return await _assess_customer_opportunity(config, model, artifact_resolver, args)

    tools["query_customer_evidence"] = Tool(
        name="query_customer_evidence", title="query_customer_evidence",
        description="Read authorized customer profiles and complete recent/sparse historical evidence; does not rank customers.",
        parameters=query_schema, handler=query_handler,
    )
    tools["assess_customer_opportunity"] = Tool(
        name="assess_customer_opportunity", title="assess_customer_opportunity",
        description="Resolve trusted opportunity/evidence references and return auditable model-inference categories.",
        parameters=assess_schema, handler=assess_handler,
    )
    return tools["query_customer_evidence"], tools["assess_customer_opportunity"]


def _await_sync(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    outcome: list[Any] = []
    failure: list[BaseException] = []

    def run() -> None:
        try:
            outcome.append(asyncio.run(value))
        except BaseException as exc:  # surfaced to CapabilityExecutor
            failure.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join()
    if failure:
        raise failure[0]
    return outcome[0]


def _quote_source(event: Mapping[str, Any]) -> str | None:
    statement = event.get("customer_statement")
    if isinstance(statement, str):
        return statement
    material = event.get("material")
    if isinstance(material, Mapping) and isinstance(material.get("title"), str):
        return material["title"]
    return None


def _validate_assessments(
    assessments: Any,
    packages: list[dict[str, Any]],
    opportunity: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(assessments, list) or len(assessments) != len(packages):
        raise CustomerSelectionProtocolError("assessment cardinality does not match evidence packages")
    by_customer = {item["customer"]["customer_id"]: item for item in packages}
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    required = {
        "customer_id", "opportunity_relevance", "need_state", *_EVIDENCE_ROLES,
        "need_summary", "suggested_tier", "reason", "information_to_verify",
    }
    for raw in assessments:
        if not isinstance(raw, dict) or set(raw) != required:
            raise CustomerSelectionProtocolError("assessment fields are invalid")
        customer_id = raw["customer_id"]
        if customer_id not in by_customer or customer_id in seen:
            raise CustomerSelectionProtocolError("assessment customer is unknown or duplicated")
        seen.add(customer_id)
        if raw["opportunity_relevance"] not in _RELEVANCE or raw["need_state"] not in _NEED_STATES or raw["suggested_tier"] not in _TIERS:
            raise CustomerSelectionProtocolError("assessment category is invalid")
        if not isinstance(raw["reason"], str) or not raw["reason"].strip() or not isinstance(raw["information_to_verify"], list) or not all(isinstance(x, str) and x.strip() for x in raw["information_to_verify"]):
            raise CustomerSelectionProtocolError("assessment explanation is invalid")
        package = by_customer[customer_id]
        events = {event["event_id"]: event for event in (*package["historical_events"], *package["recent_events"])}
        has_statement_support = False
        supporting_events: list[Mapping[str, Any]] = []
        for role in _EVIDENCE_ROLES:
            refs = raw[role]
            if not isinstance(refs, list):
                raise CustomerSelectionProtocolError("evidence references must be arrays")
            for ref in refs:
                if not isinstance(ref, dict) or set(ref) != {"event_id", "quote"}:
                    raise CustomerSelectionProtocolError("evidence reference fields are invalid")
                event = events.get(ref["event_id"])
                source = _quote_source(event) if event is not None else None
                if source is None or not isinstance(ref["quote"], str) or not ref["quote"] or ref["quote"] not in source:
                    raise CustomerSelectionProtocolError("evidence reference or verbatim quote is invalid")
                if role == "supporting_evidence":
                    supporting_events.append(event)
                    if event.get("customer_statement"):
                        has_statement_support = True
        expected_tier = _TIER_FOR_STATE.get(raw["need_state"])
        if raw["opportunity_relevance"] != "related":
            expected_tier = None
        if raw["suggested_tier"] != expected_tier:
            raise CustomerSelectionProtocolError("need state and tier are inconsistent")
        if expected_tier in {"priority", "further"} and not has_statement_support:
            raise CustomerSelectionProtocolError("priority/further tier requires cited customer language")
        if expected_tier is not None and not raw["supporting_evidence"]:
            raise CustomerSelectionProtocolError("positive tier requires supporting evidence")
        if expected_tier == "priority" and raw["contradicting_evidence"]:
            raise CustomerSelectionProtocolError("priority tier cannot retain unresolved contradiction")
        if expected_tier == "priority":
            if not any(event.get("statement_kind") == "explicit_interest" for event in supporting_events):
                raise CustomerSelectionProtocolError("priority requires a cited source expression beyond a general question")
            scope = opportunity.get("evidence_scope")
            topics = set(scope.get("topic_codes", [])) if isinstance(scope, Mapping) else set()
            if not topics:
                raise CustomerSelectionProtocolError("opportunity must declare controlled topic_codes for evidence consistency")
            support_times = [
                _parse_time(event["occurred_at"], event["event_id"])
                for event in supporting_events if event.get("topic_code") in topics
            ]
            if not support_times:
                raise CustomerSelectionProtocolError("priority support is outside the opportunity topic scope")
            latest_support = max(support_times)
            later_negative = [
                event for event in package["recent_events"]
                if event.get("topic_code") in topics
                and event.get("statement_kind") in {"not_now", "already_arranged"}
                and _parse_time(event["occurred_at"], event["event_id"]) > latest_support
            ]
            if later_negative:
                raise CustomerSelectionProtocolError("priority cannot ignore a later same-topic negative or resolved record")
        if expected_tier == "priority" and package["coverage"].get("truncated"):
            raise CustomerSelectionProtocolError("priority tier requires complete evidence")
        validated.append(dict(raw))
    if seen != set(by_customer):
        raise CustomerSelectionProtocolError("not every evidence package was assessed")
    return validated


def make_customer_targeting_handler(
    config: CustomerSelectionConfig,
    *,
    model: ChatModel,
    artifact_store: ArtifactStore,
) -> Callable[[CapabilityRequest], CapabilityResult]:
    """Create the callable ``customer_targeting`` Capability implementation."""
    resolver = lambda ref: artifact_store.get(ref).value
    query_tool, assess_tool = build_customer_selection_tools(config, model=model, artifact_resolver=resolver)

    def failed(request: CapabilityRequest, code: str, message: str, category: ErrorCategory = ErrorCategory.VALIDATION) -> CapabilityResult:
        return CapabilityResult(
            request_id=request.request_id, capability_id=request.capability_id,
            status=CapabilityStatus.FAILED,
            errors=(CapabilityError(category, code, message, retryable=False),),
        )

    def handler(request: CapabilityRequest) -> CapabilityResult:
        if request.actor_context.actor_id != config.actor_id or request.actor_context.channel_id != config.channel_id:
            return failed(request, "CUSTOMER_SCOPE_FORBIDDEN", "Capability actor/channel does not match the trusted snapshot scope.", ErrorCategory.ACCESS)
        if request.capability_id != "customer_targeting" or len(request.input_refs) != 1 or not request.input_refs[0].startswith("opportunity:"):
            return failed(request, "CUSTOMER_TARGETING_INPUT_INVALID", "Exactly one opportunity reference is required.")
        opportunity_ref = request.input_refs[0]
        try:
            opportunity = resolver(opportunity_ref)
            binding = opportunity.get("data_source")
            if not isinstance(binding, Mapping) or (binding.get("dataset_id"), binding.get("version")) != (config.dataset_id, config.dataset_version):
                raise CustomerSelectionProtocolError("opportunity and customer evidence are not bound to the same snapshot")
            goal_ref = opportunity.get("goal_ref")
            if goal_ref != {"goal_id": request.goal_ref.goal_id, "version": request.goal_ref.version}:
                raise CustomerSelectionProtocolError("opportunity is not bound to the current Goal")
            query_result = query_tool.handler({})
            if query_result.get("status") != "ok":
                error = query_result.get("error") or {}
                return failed(request, error.get("code", "CUSTOMER_EVIDENCE_FAILED"), error.get("message", "Customer evidence query failed."), ErrorCategory.DEPENDENCY)
            packages = query_result["data"]["customers"]
            evidence_refs = []
            for package in packages:
                customer_id = package["customer"]["customer_id"]
                artifact_id = f"{request.request_id}_{customer_id}"
                evidence_refs.append(artifact_store.put("customer_evidence", artifact_id, package))
            observed_at = request.as_of.isoformat() if request.as_of else _bound_snapshot(config).manifest["analysis_as_of"]
            assessment_result = _await_sync(assess_tool.handler({
                "opportunity_ref": opportunity_ref,
                "customer_evidence_refs": evidence_refs,
                "observed_at": observed_at,
            }))
            if assessment_result.get("status") != "ok":
                error = assessment_result.get("error") or {}
                category = ErrorCategory.DEPENDENCY if error.get("code") == "MODEL_CALL_FAILED" else ErrorCategory.VALIDATION
                return failed(request, error.get("code", "MODEL_ASSESSMENT_FAILED"), error.get("message", "Customer assessment failed."), category)
            assessments = _validate_assessments(assessment_result["data"]["assessments"], packages, opportunity)
            profiles = {item["customer"]["customer_id"]: item["customer"] for item in packages}
            tiers = {"priority": [], "further": [], "continued": []}
            excluded = []
            for assessment in assessments:
                entry = {
                    "customer_id": assessment["customer_id"],
                    "display_name": profiles[assessment["customer_id"]]["display_name"],
                    "opportunity_ref": opportunity_ref,
                    "inference_type": "model_inference",
                    "opportunity_relevance": assessment["opportunity_relevance"],
                    "need_state": assessment["need_state"],
                    "need_summary": assessment["need_summary"],
                    "evidence": {role: assessment[role] for role in _EVIDENCE_ROLES},
                    "reason": assessment["reason"],
                    "information_to_verify": assessment["information_to_verify"],
                }
                tier = assessment["suggested_tier"]
                (tiers[tier] if tier is not None else excluded).append(entry)
            if not tiers["priority"]:
                return CapabilityResult(
                    request_id=request.request_id, capability_id=request.capability_id,
                    status=CapabilityStatus.NO_RESULT,
                    limitations=("No customer passed the evidence and priority-tier publication constraints.",),
                )
            selection_id = f"selection_{request.request_id}"
            customer_set_id = f"priority_{request.request_id}"
            source = query_result["sources"][0]
            selection = {
                "selection_id": selection_id,
                "opportunity_ref": opportunity_ref,
                "fact_source": source,
                "tiers": tiers,
                "excluded": excluded,
                "featured_customer_id": tiers["priority"][0]["customer_id"],
                "audit": assessment_result["data"]["audit"],
                "validation": {
                    "result_type": "program_validation",
                    "checks": ["structure", "reference_exists", "same_customer", "verbatim_quote", "time_coverage", "tier_state_consistency"],
                    "semantic_correctness_proven": False,
                },
            }
            handoff = {
                "customer_set_id": customer_set_id,
                "opportunity_ref": opportunity_ref,
                "source_selection_ref": f"selection_result:{selection_id}",
                "customers": tiers["priority"],
                "scope_note": "Only priority customers are handed to downstream strategy generation.",
            }
            artifact_store.put("selection_result", selection_id, selection)
            artifact_store.put("customer_set", customer_set_id, handoff)
            return CapabilityResult(
                request_id=request.request_id, capability_id=request.capability_id,
                status=CapabilityStatus.SUCCESS,
                outputs=(
                    CapabilityOutput(selection_id, "selection_result", "Three-tier customer selection; model inference validated against source references."),
                    CapabilityOutput(customer_set_id, "customer_set", "Priority-only downstream customer set."),
                ),
                limitations=("Model semantic quality requires independent evaluation; deterministic validation does not prove meaning.",),
            )
        except CustomerSelectionProtocolError as exc:
            return failed(request, "CUSTOMER_ASSESSMENT_INVALID", str(exc))
        except Exception as exc:
            return failed(request, "CUSTOMER_TARGETING_FAILED", str(exc), ErrorCategory.INTERNAL)

    return handler


CUSTOMER_TARGETING_IO = CapabilityIO(
    required_inputs=("opportunity",),
    output_types=("selection_result", "customer_set"),
)


__all__ = [
    "CUSTOMER_TARGETING_IO",
    "CustomerSelectionConfig",
    "CustomerSelectionProtocolError",
    "build_customer_selection_tools",
    "make_customer_targeting_handler",
]