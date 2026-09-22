"""Read-only knowledge and record tools for the M4 synthetic snapshot.

The module deliberately keeps business interpretation out of the tools.  It
only resolves registered documents, reads their source text, or calculates
statistics from the two registered logical record sources.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from src.agent.tool import Tool


_ISO = "%Y-%m-%dT%H:%M:%S%z"
_HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ERRORS = {
    "INVALID_ARGUMENT",
    "RESOURCE_NOT_FOUND",
    "RESOURCE_AMBIGUOUS",
    "RESOURCE_FORBIDDEN",
    "SOURCE_CHANGED",
    "SOURCE_INVALID",
    "UNSUPPORTED_FIELD",
    "UNSUPPORTED_QUERY",
    "RESULT_TOO_LARGE",
    "INTERNAL_ERROR",
}
_AGE_BANDS = (
    ("25-34", 25, 34),
    ("35-44", 35, 44),
    ("45-54", 45, 54),
    ("55-64", 55, 64),
    ("65-74", 65, 74),
)
_BEHAVIOR_FIELDS = {
    "age_years",
    "age_band",
    "family_stage",
    "topic_code",
    "event_type",
    "statement_kind",
}
_PROFILE_FIELDS = {"age_years", "age_band", "family_stage"}
_EVENT_FILTER_FIELDS = {"topic_code", "event_type", "statement_kind"}
_OPS = {
    "age_years": {"eq", "gte", "lte"},
    "age_band": {"eq", "in"},
    "family_stage": {"eq", "in", "is_null"},
    "topic_code": {"eq", "in"},
    "event_type": {"eq", "in"},
    "statement_kind": {"eq", "in", "is_null"},
}


class _SourceChanged(Exception):
    pass


@dataclass(frozen=True, slots=True)
class InsightToolConfig:
    """Trusted application-owned data bindings; never model-supplied."""

    client_root: Path
    product_root: Path
    tool_version: str = "insight-tools-v1"
    excerpt_limit: int = 600
    max_read_lines: int = 120
    max_groups: int = 100

    @classmethod
    def from_repository(cls, repository_root: Path) -> "InsightToolConfig":
        data_root = repository_root / "data"
        return cls(data_root / "client", data_root / "product")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_no} is not an object")
        rows.append(value)
    return rows


def _envelope(config: InsightToolConfig, status: str, data: Any, sources: list[dict[str, Any]],
              *, warnings: list[str] | None = None, error: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "data": data,
        "sources": sources,
        "meta": {"tool_version": config.tool_version},
        "warnings": warnings or [],
        "error": error,
    }


def _error(config: InsightToolConfig, code: str, message: str, sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if code not in _ERRORS:
        code = "INTERNAL_ERROR"
    return _envelope(config, "error", None, sources or [], error={"code": code, "message": message})


def _resource_file(config: InsightToolConfig, entry: Mapping[str, Any]) -> Path:
    path = (config.product_root.parent.parent / entry["document_path"]).resolve()
    root = config.product_root.resolve()
    if path != root / path.name and root not in path.parents:
        raise PermissionError("document is outside the authorized product root")
    return path


class _Snapshot:
    def __init__(self, config: InsightToolConfig) -> None:
        self.config = config
        self.manifest = json.loads((config.client_root / "manifest.json").read_text(encoding="utf-8"))
        self.customers = _jsonl(config.client_root / "customers.jsonl")
        self.events = _jsonl(config.client_root / "behaviors.jsonl")
        self.topics = json.loads((config.client_root / "topics.json").read_text(encoding="utf-8"))
        self.materials = json.loads((config.client_root / "materials.json").read_text(encoding="utf-8"))
        self.catalog = json.loads((config.product_root / "product_catalog.json").read_text(encoding="utf-8"))
        self._validate()

    def _validate(self) -> None:
        required = ("dataset_id", "version", "analysis_as_of", "window_start", "window_end", "channel_id", "owner_actor_id")
        if self.manifest.get("synthetic") is not True or any(key not in self.manifest for key in required):
            raise ValueError("manifest is incomplete")
        identity = (self.manifest["dataset_id"], self.manifest["version"])
        for label, document in (("topics", self.topics), ("materials", self.materials), ("product_catalog", self.catalog)):
            if (document.get("dataset_id"), document.get("version")) != identity:
                raise ValueError(f"{label} snapshot identity does not match manifest")
        files = {
            "client/customers.jsonl": self.config.client_root / "customers.jsonl",
            "client/behaviors.jsonl": self.config.client_root / "behaviors.jsonl",
            "client/topics.json": self.config.client_root / "topics.json",
            "client/materials.json": self.config.client_root / "materials.json",
            "product/product_catalog.json": self.config.product_root / "product_catalog.json",
            "client/README.md": self.config.client_root / "README.md",
        }
        for name, expected in self.manifest.get("file_sha256", {}).items():
            if name not in files or not files[name].exists() or _sha256(files[name]) != expected:
                raise ValueError(f"source fingerprint mismatch: {name}")
        customer_ids = [row.get("customer_id") for row in self.customers]
        event_ids = [row.get("event_id") for row in self.events]
        source_ids = [row.get("source_record_id") for row in self.events]
        if not customer_ids or len(set(customer_ids)) != len(customer_ids) or len(set(event_ids)) != len(event_ids) or len(set(source_ids)) != len(source_ids):
            raise ValueError("source identifiers are not unique")
        known = set(customer_ids)
        for customer in self.customers:
            if customer.get("channel_id") != self.manifest["channel_id"] or customer.get("owner_actor_id") != self.manifest["owner_actor_id"]:
                raise ValueError("customer scope does not match manifest")
            if not isinstance(customer.get("age_years"), int) or customer["age_years"] < 0:
                raise ValueError("invalid customer age")
        for event in self.events:
            if event.get("customer_id") not in known:
                raise ValueError("event references unknown customer")
            _parse_time(event.get("occurred_at"), event.get("event_id", "event"))

    def source(self, source_id: str) -> dict[str, Any]:
        return {
            "source_id": source_id,
            "dataset_id": self.manifest["dataset_id"],
            "version": self.manifest["version"],
            "synthetic": self.manifest["synthetic"],
            "manifest_sha256": _sha256(self.config.client_root / "manifest.json"),
        }

    def customer_map(self) -> dict[str, dict[str, Any]]:
        return {row["customer_id"]: row for row in self.customers}


def _sections(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    found: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines, 1):
        match = _HEAD_RE.match(line)
        if match:
            found.append((index, len(match.group(1)), match.group(2).strip()))
    sections: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []
    for pos, (start, level, title) in enumerate(found):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        end = found[pos + 1][0] - 1 if pos + 1 < len(found) else len(lines)
        sections.append({
            "start": start, "end": end, "title": title,
            "path": [item[1] for item in stack],
            "text": "\n".join(lines[start - 1:end]),
        })
    return sections


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _resolve_resources(snapshot: _Snapshot, names: list[str] | None) -> list[dict[str, Any]]:
    entries = snapshot.catalog.get("products", [])
    if names is None:
        return list(entries)
    selected: list[dict[str, Any]] = []
    for name in names:
        matches = [entry for entry in entries if name in {entry.get("product_id"), entry.get("display_name"), *entry.get("aliases", [])}]
        if not matches:
            raise LookupError(f"unknown resource name: {name}")
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous resource name: {name}")
        if matches[0] not in selected:
            selected.append(matches[0])
    return selected


def _search_knowledge(config: InsightToolConfig, arguments: Mapping[str, Any]) -> dict[str, Any]:
    try:
        snapshot = _Snapshot(config)
        resources = _resolve_resources(snapshot, arguments.get("resource_names"))
        terms = [str(term) for term in arguments["terms"]]
        match = arguments.get("match", "any")
        limit = arguments.get("limit", 5)
        hits: list[dict[str, Any]] = []
        for entry in resources:
            path = _resource_file(config, entry)
            if not path.exists():
                raise FileNotFoundError(str(path))
            if _sha256(path) != entry["document_sha256"]:
                raise _SourceChanged(f"document fingerprint changed: {entry['product_id']}")
            text = path.read_text(encoding="utf-8")
            for section in _sections(text):
                haystack = _norm(section["text"])
                matched = [term for term in terms if _norm(term) in haystack]
                if (match == "all" and len(matched) != len(terms)) or (match == "any" and not matched):
                    continue
                excerpt = section["text"]
                truncated = len(excerpt) > config.excerpt_limit
                if truncated:
                    excerpt = excerpt[:config.excerpt_limit]
                hits.append({
                    "doc_id": entry["product_id"],
                    "document_title": entry["display_name"],
                    "document_sha256": entry["document_sha256"],
                    "section_id": f"{entry['product_id']}:{section['start']}",
                    "heading_path": section["path"],
                    "line_start": section["start"], "line_end": section["end"],
                    "matched_terms": matched, "excerpt": excerpt,
                    "excerpt_truncated": truncated,
                    "_score": (len(matched), sum(_norm(term) in _norm(section["title"]) for term in matched)),
                })
        for item in hits:
            item["_sort_score"] = item.pop("_score")
        hits.sort(key=lambda item: (-item["_sort_score"][0], -item["_sort_score"][1], item["doc_id"], item["line_start"]))
        for item in hits:
            item.pop("_sort_score", None)
        returned = hits[:limit]
        data = {"matches": returned, "total_matches": len(hits), "returned_count": len(returned), "truncated": len(hits) > limit}
        sources = [snapshot.source(f"knowledge:{entry['product_id']}") | {"document_sha256": entry["document_sha256"]} for entry in resources]
        return _envelope(config, "ok" if hits else "empty", data, sources)
    except LookupError as exc:
        return _error(config, "RESOURCE_NOT_FOUND", str(exc))
    except RuntimeError as exc:
        return _error(config, "RESOURCE_AMBIGUOUS", str(exc))
    except PermissionError as exc:
        return _error(config, "RESOURCE_FORBIDDEN", str(exc))
    except _SourceChanged as exc:
        return _error(config, "SOURCE_CHANGED", str(exc))
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return _error(config, "SOURCE_INVALID", str(exc))


def _read_knowledge(config: InsightToolConfig, arguments: Mapping[str, Any]) -> dict[str, Any]:
    try:
        snapshot = _Snapshot(config)
        matches = [entry for entry in snapshot.catalog.get("products", []) if entry.get("product_id") == arguments["doc_id"]]
        if not matches:
            return _error(config, "RESOURCE_NOT_FOUND", f"unknown doc_id: {arguments['doc_id']}")
        entry = matches[0]
        if arguments["line_end"] - arguments["line_start"] + 1 > config.max_read_lines:
            return _error(config, "RESULT_TOO_LARGE", f"line range exceeds {config.max_read_lines} lines")
        path = _resource_file(config, entry)
        actual_sha = _sha256(path)
        if actual_sha != arguments["document_sha256"]:
            return _error(config, "SOURCE_CHANGED", "document fingerprint does not match; search again")
        lines = path.read_text(encoding="utf-8").splitlines()
        if arguments["line_start"] < 1 or arguments["line_end"] > len(lines):
            return _error(config, "INVALID_ARGUMENT", "line range is outside the document")
        selected = "\n".join(lines[arguments["line_start"] - 1:arguments["line_end"]])
        sections = _sections(path.read_text(encoding="utf-8"))
        path_at_line = next((section["path"] for section in reversed(sections) if section["start"] <= arguments["line_start"]), [])
        data = {"doc_id": entry["product_id"], "document_title": entry["display_name"], "document_sha256": actual_sha,
                "line_start": arguments["line_start"], "line_end": arguments["line_end"], "heading_path": path_at_line, "text": selected}
        return _envelope(config, "ok", data, [snapshot.source(f"knowledge:{entry['product_id']}") | {"document_sha256": actual_sha}])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError, PermissionError) as exc:
        return _error(config, "SOURCE_INVALID", str(exc))


def _band(age: Any) -> str:
    if not isinstance(age, int):
        return "unknown"
    for label, lower, upper in _AGE_BANDS:
        if lower <= age <= upper:
            return label
    return "other"


def _condition_value(row: Mapping[str, Any], field: str, customer: Mapping[str, Any] | None) -> Any:
    if field == "age_years":
        return (customer or row).get("age_years")
    if field == "age_band":
        return _band((customer or row).get("age_years"))
    if field == "family_stage":
        return (customer or row).get("family_stage")
    return row.get(field)


def _matches(row: Mapping[str, Any], filters: list[Mapping[str, Any]], customer: Mapping[str, Any] | None) -> bool:
    for item in filters:
        field, op, expected = item["field"], item["op"], item.get("value")
        actual = _condition_value(row, field, customer)
        if op == "is_null":
            ok = actual is None
        elif op == "eq":
            ok = actual == expected
        elif op == "gte":
            ok = actual is not None and actual >= expected
        elif op == "lte":
            ok = actual is not None and actual <= expected
        else:
            ok = actual in expected
        if not ok:
            return False
    return True


def _validate_filter(item: Mapping[str, Any], source_id: str) -> None:
    field, op = item.get("field"), item.get("op")
    allowed = _PROFILE_FIELDS if source_id == "customer_profiles" else _BEHAVIOR_FIELDS
    if field not in allowed:
        raise LookupError(f"unsupported field: {field}")
    if op not in _OPS[field]:
        raise ValueError(f"unsupported operation for {field}: {op}")
    if op == "is_null":
        if "value" in item:
            raise ValueError("is_null must not include value")
    elif "value" not in item:
        raise ValueError(f"{op} requires value")
    elif op == "in" and (not isinstance(item["value"], list) or not item["value"]):
        raise ValueError("in requires a non-empty list")
    if op != "is_null" and "value" in item:
        value = item["value"]
        values = value if op == "in" else [value]
        if field == "age_years" and any(not isinstance(item_value, int) or isinstance(item_value, bool) for item_value in values):
            raise ValueError("age_years requires integer values")
        if field != "age_years" and any(item_value is not None and not isinstance(item_value, str) for item_value in values):
            raise ValueError(f"{field} requires string values")


def _aggregate_records(config: InsightToolConfig, arguments: Mapping[str, Any]) -> dict[str, Any]:
    try:
        snapshot = _Snapshot(config)
        source_id = arguments["source_id"]
        filters = list(arguments.get("filters", []))
        metrics = set(arguments["metrics"])
        if source_id == "customer_profiles" and "event_count" in metrics:
            raise RuntimeError("event_count is only supported for customer_behaviors")
        for item in filters:
            _validate_filter(item, source_id)
        group_by = list(arguments.get("group_by", []))
        allowed_groups = _PROFILE_FIELDS - {"age_years"} if source_id == "customer_profiles" else _BEHAVIOR_FIELDS - {"age_years"}
        if any(field not in allowed_groups for field in group_by):
            raise LookupError("unsupported group_by field")
        if len(group_by) > 2 or len(set(group_by)) != len(group_by):
            raise ValueError("group_by must contain at most two unique fields")
        if len(set(arguments["metrics"])) != len(arguments["metrics"]):
            raise ValueError("metrics must not contain duplicates")
        customers = snapshot.customer_map()
        start = end = None
        if source_id == "customer_behaviors":
            time_range = arguments.get("time_range")
            start, end = _parse_time(time_range["start"], "time_range.start"), _parse_time(time_range["end"], "time_range.end")
            if start >= end:
                raise ValueError("time_range.start must precede end")
            rows = [row for row in snapshot.events if start <= _parse_time(row["occurred_at"], row["event_id"]) < end]
            candidates = [row for row in rows if _matches(row, filters, customers[row["customer_id"]])]
            population = [customer for customer in snapshot.customers if _matches(customer, [item for item in filters if item["field"] in _PROFILE_FIELDS], None)]
            metric_customers = {row["customer_id"] for row in candidates}
        else:
            if arguments.get("time_range") is not None:
                raise ValueError("customer_profiles does not accept time_range")
            rows = list(snapshot.customers)
            candidates = [row for row in rows if _matches(row, filters, None)]
            population = candidates
            metric_customers = {row["customer_id"] for row in candidates}
        if len(group_by) == 0:
            grouped = {(): candidates}
        else:
            grouped = defaultdict(list)
            for row in candidates:
                customer = customers.get(row["customer_id"]) if source_id == "customer_behaviors" else None
                grouped[tuple(_condition_value(row, field, customer) for field in group_by)].append(row)
            if len(grouped) > config.max_groups:
                return _error(config, "RESULT_TOO_LARGE", f"group result exceeds {config.max_groups} groups", [snapshot.source(source_id)])
        def measures(items: list[Mapping[str, Any]]) -> dict[str, int]:
            values: dict[str, int] = {}
            if "event_count" in metrics:
                values["event_count"] = len(items)
            if "distinct_customers" in metrics:
                values["distinct_customers"] = len({item["customer_id"] for item in items}) if source_id == "customer_behaviors" else len({item["customer_id"] for item in items})
            return values
        rows_out = []
        for key, items in grouped.items():
            row = {field: value for field, value in zip(group_by, key)}
            row.update(measures(items))
            rows_out.append(row)
        rows_out.sort(key=lambda row: tuple("" if row.get(field) is None else str(row.get(field)) for field in group_by))
        missing_fields = sorted({item["field"] for item in filters} | set(group_by))
        missing = {field: {"count": sum(_condition_value(row, field, customers.get(row["customer_id"])) is None if source_id == "customer_behaviors" else _condition_value(row, field, None) is None for row in rows),
                           "unit": "events" if source_id == "customer_behaviors" else "customers", "stage": "time_and_scope"} for field in missing_fields}
        data = {
            "rows": rows_out,
            "totals": measures(candidates),
            "population_customers": len({customer["customer_id"] for customer in population}),
            "matched_customers": len(metric_customers),
            "normalized_query": {"source_id": source_id, "time_range": arguments.get("time_range"), "filters": filters, "group_by": group_by, "metrics": arguments["metrics"], "age_band_version": "m4-five-bands-v1"},
            "missing": missing,
        }
        warnings = ["Synthetic snapshot; counts are observations, not needs, recommendations, or forecasts."]
        if source_id == "customer_behaviors":
            warnings.append("Age and family_stage are snapshot attributes, not values at event time.")
        return _envelope(config, "ok", data, [snapshot.source(source_id)], warnings=warnings)
    except LookupError as exc:
        return _error(config, "UNSUPPORTED_FIELD", str(exc))
    except RuntimeError as exc:
        return _error(config, "UNSUPPORTED_QUERY", str(exc))
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _error(config, "SOURCE_INVALID" if isinstance(exc, (FileNotFoundError, json.JSONDecodeError)) else "INVALID_ARGUMENT", str(exc))


def build_insight_tools(config: InsightToolConfig) -> tuple[Tool, Tool, Tool]:
    """Build the three independently callable Tool objects."""

    schemas: dict[str, dict[str, Any]] = {
        "search_knowledge": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "resource_names": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1},
                "terms": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1},
                "match": {"type": "string", "enum": ["all", "any"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            }, "required": ["terms"],
        },
        "read_knowledge": {
            "type": "object", "additionalProperties": False,
            "properties": {"doc_id": {"type": "string", "minLength": 1}, "document_sha256": {"type": "string", "pattern": "^[0-9A-Fa-f]{64}$"}, "line_start": {"type": "integer", "minimum": 1}, "line_end": {"type": "integer", "minimum": 1}},
            "required": ["doc_id", "document_sha256", "line_start", "line_end"],
        },
        "aggregate_records": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "source_id": {"type": "string", "enum": ["customer_profiles", "customer_behaviors"]},
                "time_range": {"type": ["object", "null"], "additionalProperties": False, "properties": {"start": {"type": "string", "format": "date-time"}, "end": {"type": "string", "format": "date-time"}}, "required": ["start", "end"]},
                "filters": {"type": "array", "maxItems": 20, "items": {"type": "object", "additionalProperties": False, "properties": {"field": {"type": "string"}, "op": {"type": "string"}, "value": {}}, "required": ["field", "op"]}},
                "group_by": {"type": "array", "maxItems": 2, "items": {"type": "string"}},
                "metrics": {"type": "array", "items": {"type": "string", "enum": ["event_count", "distinct_customers"]}, "minItems": 1},
            }, "required": ["source_id", "metrics"],
        },
    }
    implementations: dict[str, Callable[[InsightToolConfig, Mapping[str, Any]], dict[str, Any]]] = {
        "search_knowledge": _search_knowledge, "read_knowledge": _read_knowledge, "aggregate_records": _aggregate_records,
    }
    tools: list[Tool] = []
    by_name: dict[str, Tool] = {}

    def handler(name: str, args: Mapping[str, Any]) -> dict[str, Any]:
        tool = by_name[name]
        try:
            tool.validate_arguments(args)
        except ValueError as exc:
            return _error(config, "INVALID_ARGUMENT", str(exc))
        if name == "read_knowledge" and args["line_start"] > args["line_end"]:
            return _error(config, "INVALID_ARGUMENT", "line_start must not exceed line_end")
        return implementations[name](config, args)

    descriptions = {
        "search_knowledge": "Search registered Markdown knowledge by explicit terms; returns source excerpts only.",
        "read_knowledge": "Read an exact line range from a registered Markdown document after fingerprint verification.",
        "aggregate_records": "Calculate allowlisted read-only counts from registered customer or behavior records.",
    }
    for name in ("search_knowledge", "read_knowledge", "aggregate_records"):
        tool = Tool(name=name, title=name, description=descriptions[name], parameters=schemas[name], handler=lambda args, n=name: handler(n, args))
        tools.append(tool)
        by_name[name] = tool
    return tuple(tools)  # type: ignore[return-value]


__all__ = ["InsightToolConfig", "build_insight_tools"]
