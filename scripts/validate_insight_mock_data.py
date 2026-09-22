#!/usr/bin/env python3
"""Validate the shared insight/customer-selection v2 synthetic snapshot."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLIENT_DATA = ROOT / "data" / "client"
PRODUCT_CATALOG = ROOT / "data" / "product" / "product_catalog.json"
AS_OF = datetime.fromisoformat("2026-09-22T00:00:00+08:00")
WINDOW_START = datetime.fromisoformat("2026-06-24T00:00:00+08:00")
WINDOW_END = AS_OF
CHANNEL = "individual"
ACTOR = "AGENT_DEMO_001"
TOPICS = {
    "retirement_income",
    "family_protection",
    "liquidity_planning",
    "dividend_understanding",
    "health_protection",
}
EVENT_TYPES = {"content_view", "event_attendance", "consultation", "followup_note"}
STATEMENT_KINDS = {"question", "explicit_interest", "not_now", "already_arranged"}
SOURCE_TYPES = {
    "content_view": "mock_content_log",
    "event_attendance": "mock_activity_log",
    "consultation": "mock_consultation_log",
    "followup_note": "mock_followup_log",
}
EXPECTED_AGES = [25, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37, 38, 39, 40, 40, 41, 42, 42, 43, 44,
                 45, 46, 46, 47, 48, 48, 49, 50, 50, 51, 52, 52, 53, 54, 55, 56, 57, 58, 59, 60,
                 61, 62, 63, 64, 65, 66, 68, 70, 72, 74]
EXPECTED = {
    "customers": 50,
    "events": 117,
    "recent_events": 107,
    "historical_events": 10,
    "recent_active_customers": 40,
    "historical_only_customers": 5,
    "no_event_customers": 5,
    "recent_consultation_customers": 20,
    "recent_explicit_interest_customers": 13,
    "recent_not_now_customers": 6,
    "recent_already_arranged_customers": 2,
    "recent_cross_topic_customers": 5,
    "event_type_counts": {"content_view": 65, "event_attendance": 10, "consultation": 25, "followup_note": 17},
    "recent_event_type_counts": {"content_view": 60, "event_attendance": 10, "consultation": 20, "followup_note": 17},
    "recent_topic_customers": {
        "retirement_income": 13, "family_protection": 10, "liquidity_planning": 8,
        "dividend_understanding": 7, "health_protection": 7,
    },
    "recent_topic_consultation_customers": {
        "retirement_income": 9, "family_protection": 5, "liquidity_planning": 3,
        "dividend_understanding": 2, "health_protection": 1,
    },
    "recent_topic_explicit_interest_customers": {
        "retirement_income": 6, "family_protection": 4, "liquidity_planning": 2,
        "dividend_understanding": 1, "health_protection": 0,
    },
}

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{path.name}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise AssertionError(f"{path.name}:{line_no}: row is not an object")
        rows.append(value)
    return rows

def parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AssertionError(f"{label}: invalid ISO timestamp {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=8):
        raise AssertionError(f"{label}: timestamp must carry +08:00")
    return parsed

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def assert_unique(rows: list[dict[str, Any]], field: str, label: str) -> None:
    values = [row.get(field) for row in rows]
    if any(value in (None, "") for value in values):
        raise AssertionError(f"{label}: blank {field}")
    duplicates = [value for value, count in Counter(values).items() if count > 1]
    if duplicates:
        raise AssertionError(f"{label}: duplicate {field}: {duplicates}")

def recent(event: dict[str, Any]) -> bool:
    timestamp = parse_time(event["occurred_at"], event["event_id"])
    return WINDOW_START <= timestamp < WINDOW_END

def event_customer_sets(events: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    recent_ids = {event["customer_id"] for event in events if recent(event)}
    historical_ids = {event["customer_id"] for event in events if not recent(event)}
    return recent_ids, historical_ids

def validate_files() -> dict[str, Any]:
    customers = load_jsonl(CLIENT_DATA / "customers.jsonl")
    events = load_jsonl(CLIENT_DATA / "behaviors.jsonl")
    topics_doc = json.loads((CLIENT_DATA / "topics.json").read_text(encoding="utf-8"))
    materials_doc = json.loads((CLIENT_DATA / "materials.json").read_text(encoding="utf-8"))
    catalog = json.loads(PRODUCT_CATALOG.read_text(encoding="utf-8"))
    manifest_path = CLIENT_DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    if manifest is None:
        raise AssertionError("manifest.json is required")
    for key, expected in {
        "dataset_id": "insight_demo_v2", "version": "2.0", "synthetic": True,
        "analysis_as_of": "2026-09-22T00:00:00+08:00", "timezone": "Asia/Shanghai",
        "window_start": "2026-06-24T00:00:00+08:00", "window_end": "2026-09-22T00:00:00+08:00",
        "channel_id": CHANNEL, "owner_actor_id": ACTOR,
    }.items():
        if manifest.get(key) != expected:
            raise AssertionError(f"manifest {key}: {manifest.get(key)!r} != {expected!r}")

    if len(customers) != EXPECTED["customers"]:
        raise AssertionError(f"customers count: {len(customers)}")
    if len(events) != EXPECTED["events"]:
        raise AssertionError(f"events count: {len(events)}")
    assert_unique(customers, "customer_id", "customers")
    assert_unique(events, "event_id", "behaviors")
    assert_unique(events, "source_record_id", "behaviors")

    customer_ids = {row["customer_id"] for row in customers}
    expected_ids = {f"C{i:03d}" for i in range(1, 51)}
    if customer_ids != expected_ids:
        raise AssertionError("customer_id set must be exactly C001-C050")
    if [row["age_years"] for row in customers] != [EXPECTED_AGES[(17 * i) % 50] for i in range(50)]:
        raise AssertionError("customer age permutation does not match M4 design")
    for customer in customers:
        if customer["display_name"] != f"模拟客户{customer['customer_id'][1:]}":
            raise AssertionError(f"display_name mismatch for {customer['customer_id']}")
        if customer["family_stage"] is not None:
            raise AssertionError("family_stage must be null for every customer")
        if customer["channel_id"] != CHANNEL or customer["owner_actor_id"] != ACTOR:
            raise AssertionError(f"customer scope mismatch for {customer['customer_id']}")
        if customer["source_record_id"] != f"PROFILE_{customer['customer_id']}":
            raise AssertionError(f"profile source mismatch for {customer['customer_id']}")

    topic_rows = topics_doc.get("topics", [])
    topic_ids = {row["topic_code"] for row in topic_rows}
    if topic_ids != TOPICS or len(topic_rows) != 5:
        raise AssertionError("topics dictionary must contain exactly five topic codes")
    material_rows = materials_doc.get("materials", [])
    materials = {row["material_id"]: row for row in material_rows}
    if len(material_rows) != 15 or len(materials) != 15:
        raise AssertionError("materials dictionary must contain exactly 15 unique materials")
    for row in material_rows:
        if row.get("synthetic") is not True or row.get("topic_code") not in TOPICS:
            raise AssertionError(f"invalid material metadata: {row}")
    for product in catalog.get("products", []):
        product_path = ROOT / product["document_path"]
        if not product_path.exists():
            raise AssertionError(f"missing product document: {product_path}")
        if product.get("source_kind") != "user_provided_markdown" or product.get("document_version") is not None:
            raise AssertionError("product catalog source/version metadata mismatch")
        if product["document_sha256"] != sha256(product_path):
            raise AssertionError(f"product fingerprint mismatch: {product['product_id']}")

    manifest_files = manifest.get("file_sha256", {})
    expected_manifest_files = {
        "client/customers.jsonl": sha256(CLIENT_DATA / "customers.jsonl"),
        "client/behaviors.jsonl": sha256(CLIENT_DATA / "behaviors.jsonl"),
        "client/topics.json": sha256(CLIENT_DATA / "topics.json"),
        "client/materials.json": sha256(CLIENT_DATA / "materials.json"),
        "product/product_catalog.json": sha256(PRODUCT_CATALOG),
        "client/README.md": sha256(CLIENT_DATA / "README.md"),
    }
    if manifest_files != expected_manifest_files:
        raise AssertionError(f"manifest file fingerprints mismatch: {manifest_files!r} != {expected_manifest_files!r}")
    if "manifest.json" in manifest_files:
        raise AssertionError("manifest must not contain its own fingerprint")
    archive_path = CLIENT_DATA / "versions" / "1.0-manifest.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    if archive.get("dataset_id") != "insight_demo_v1" or archive.get("version") != "1.0":
        raise AssertionError("v1 traceability manifest is missing or invalid")

    for event in events:
        event_id = event["event_id"]
        if event["customer_id"] not in customer_ids:
            raise AssertionError(f"{event_id}: unknown customer")
        if event["event_type"] not in EVENT_TYPES or event["topic_code"] not in TOPICS:
            raise AssertionError(f"{event_id}: invalid event type/topic")
        timestamp = parse_time(event["occurred_at"], event_id)
        if timestamp >= AS_OF:
            raise AssertionError(f"{event_id}: event is not before analysis_as_of")
        if event["source_type"] != SOURCE_TYPES[event["event_type"]]:
            raise AssertionError(f"{event_id}: source_type mismatch")
        if event["event_type"] in {"content_view", "event_attendance"}:
            if event["material_id"] not in materials:
                raise AssertionError(f"{event_id}: missing material reference")
            if materials[event["material_id"]]["topic_code"] != event["topic_code"]:
                raise AssertionError(f"{event_id}: material/topic mismatch")
            if event["customer_statement"] is not None or event["statement_kind"] is not None:
                raise AssertionError(f"{event_id}: content/activity must not contain customer statement")
        else:
            if event["material_id"] is not None or event["statement_kind"] not in STATEMENT_KINDS:
                raise AssertionError(f"{event_id}: consultation/followup fields invalid")
            statement = event["customer_statement"]
            if not isinstance(statement, str) or not statement.strip():
                raise AssertionError(f"{event_id}: statement is required")
            if event["statement_kind"] == "question" and "？" not in statement:
                raise AssertionError(f"{event_id}: question statement must be phrased as a question")
            if event["statement_kind"] == "explicit_interest" and not any(term in statement for term in ("希望", "我想")):
                raise AssertionError(f"{event_id}: explicit_interest statement must express first-person interest")
            if event["statement_kind"] == "not_now" and "暂不考虑" not in statement:
                raise AssertionError(f"{event_id}: not_now statement mismatch")
            if event["statement_kind"] == "already_arranged" and "已经" not in statement:
                raise AssertionError(f"{event_id}: already_arranged statement mismatch")
            age = next(row["age_years"] for row in customers if row["customer_id"] == event["customer_id"])
            if event["topic_code"] == "retirement_income":
                if age < 60 and "退休后" in statement and "未来退休" not in statement:
                    raise AssertionError(f"{event_id}: younger customer has incompatible retired wording")
                if age >= 60 and "未来退休" in statement:
                    raise AssertionError(f"{event_id}: older customer has incompatible future-retirement wording")
        forbidden = ("Opportunity", "推荐名单", "评分", "NBEV预测", "成交概率")
        if any(term in json.dumps(event, ensure_ascii=False) for term in forbidden):
            raise AssertionError(f"{event_id}: prohibited precomputed business output")

    by_event = {event["event_id"]: event for event in events}
    semantic_samples = {
        "EVT_C021_03": "给自己安排",
        "EVT_C023_03": "只是想弄清楚",
        "EVT_C024_03": "替朋友",
        "EVT_C025_04": "暂不考虑",
        "EVT_C022_04": "医疗保障",
    }
    for event_id, phrase in semantic_samples.items():
        if phrase not in by_event[event_id]["customer_statement"]:
            raise AssertionError(f"{event_id}: required semantic sample is missing")

    recent_events = [event for event in events if recent(event)]
    historical_events = [event for event in events if not recent(event)]
    recent_ids, historical_ids = event_customer_sets(events)
    no_event_ids = customer_ids - recent_ids - historical_ids
    recent_type_counts = Counter(event["event_type"] for event in recent_events)
    recent_consultation = [event for event in recent_events if event["event_type"] == "consultation"]
    recent_explicit = [event for event in recent_events if event["statement_kind"] == "explicit_interest"]
    recent_not_now = [event for event in recent_events if event["statement_kind"] == "not_now"]
    recent_arranged = [event for event in recent_events if event["statement_kind"] == "already_arranged"]
    topic_customers = {topic: {e["customer_id"] for e in recent_events if e["topic_code"] == topic} for topic in TOPICS}
    topic_consultation = {topic: {e["customer_id"] for e in recent_consultation if e["topic_code"] == topic} for topic in TOPICS}
    topic_explicit = {topic: {e["customer_id"] for e in recent_explicit if e["topic_code"] == topic} for topic in TOPICS}
    cross_topic = {customer_id for customer_id in recent_ids if len({e["topic_code"] for e in recent_events if e["customer_id"] == customer_id}) > 1}

    actual = {
        "customers": len(customers), "events": len(events),
        "recent_events": len(recent_events), "historical_events": len(historical_events),
        "recent_active_customers": len(recent_ids),
        "historical_only_customers": len(historical_ids - recent_ids),
        "no_event_customers": len(no_event_ids),
        "recent_consultation_customers": len({e["customer_id"] for e in recent_consultation}),
        "recent_explicit_interest_customers": len({e["customer_id"] for e in recent_explicit}),
        "recent_not_now_customers": len({e["customer_id"] for e in recent_not_now}),
        "recent_already_arranged_customers": len({e["customer_id"] for e in recent_arranged}),
        "recent_cross_topic_customers": len(cross_topic),
        "event_type_counts": dict(Counter(event["event_type"] for event in events)),
        "recent_event_type_counts": dict(recent_type_counts),
        "recent_topic_customers": {topic: len(ids) for topic, ids in topic_customers.items()},
        "recent_topic_consultation_customers": {topic: len(ids) for topic, ids in topic_consultation.items()},
        "recent_topic_explicit_interest_customers": {topic: len(ids) for topic, ids in topic_explicit.items()},
        "age_distribution": dict(Counter(
            "25-34" if row["age_years"] <= 34 else "35-44" if row["age_years"] <= 44 else
            "45-54" if row["age_years"] <= 54 else "55-64" if row["age_years"] <= 64 else "65-74"
            for row in customers
        )),
    }
    for key, expected in EXPECTED.items():
        if actual.get(key) != expected:
            raise AssertionError(f"{key}: actual={actual.get(key)!r}, expected={expected!r}")
    if actual["age_distribution"] != {"25-34": 8, "35-44": 12, "45-54": 14, "55-64": 10, "65-74": 6}:
        raise AssertionError(f"age distribution mismatch: {actual['age_distribution']}")

    return {"actual": actual, "files": {
        name: sha256(path)
        for name, path in {
            "client/customers.jsonl": CLIENT_DATA / "customers.jsonl",
            "client/behaviors.jsonl": CLIENT_DATA / "behaviors.jsonl",
            "client/topics.json": CLIENT_DATA / "topics.json",
            "client/materials.json": CLIENT_DATA / "materials.json",
            "product/product_catalog.json": PRODUCT_CATALOG,
            "client/README.md": CLIENT_DATA / "README.md",
        }.items()
        if path.exists()
    }, "manifest_present": manifest is not None}

def run_independent_fixtures() -> dict[str, Any]:
    events = load_jsonl(CLIENT_DATA / "behaviors.jsonl")
    customers = load_jsonl(CLIENT_DATA / "customers.jsonl")
    base_recent = {event["customer_id"] for event in events if recent(event)}
    fixtures = {}

    duplicate = copy.deepcopy(events)
    duplicate.append(copy.deepcopy(events[0]))
    duplicate[-1]["event_id"] = "FIXTURE_DUPLICATE"
    try:
        assert_unique(duplicate, "source_record_id", "duplicate fixture")
    except AssertionError:
        fixtures["duplicate_event_source_rejected"] = True

    unknown = copy.deepcopy(events)
    unknown[0]["customer_id"] = "C999"
    if unknown[0]["customer_id"] not in {row["customer_id"] for row in customers}:
        fixtures["unknown_customer_rejected"] = True

    moved = copy.deepcopy(events)
    moved[0]["occurred_at"] = WINDOW_END.isoformat()
    moved_recent = {event["customer_id"] for event in moved if recent(event)}
    if sum(recent(event) for event in moved) == sum(recent(event) for event in events) - 1:
        fixtures["window_end_excluded"] = True

    start_event = copy.deepcopy(events[0])
    start_event["occurred_at"] = WINDOW_START.isoformat()
    if recent(start_event):
        fixtures["window_start_included"] = True

    removed = [event for event in events if event["customer_id"] != "C021"]
    removed_recent = {event["customer_id"] for event in removed if recent(event)}
    if len(customers) == 50 and len(removed_recent) == len(base_recent) - 1:
        fixtures["removing_customer_events_changes_recent_count"] = True

    changed = [event for event in events if event["statement_kind"] != "explicit_interest" or event["customer_id"] != "C021"]
    changed_explicit = {event["customer_id"] for event in changed if recent(event) and event["statement_kind"] == "explicit_interest"}
    if len(changed_explicit) == EXPECTED["recent_explicit_interest_customers"] - 1:
        fixtures["removing_explicit_interest_changes_stat"] = True

    # A same-customer/same-topic extra browse changes event count but not distinct recent customer count.
    extra = copy.deepcopy(events[0])
    extra["event_id"] = "FIXTURE_EXTRA_BROWSE"
    extra["source_record_id"] = "FIXTURE_EXTRA_BROWSE_SOURCE"
    extra["occurred_at"] = WINDOW_START.isoformat()
    events_plus = events + [extra]
    if len(events_plus) == len(events) + 1 and len({event["customer_id"] for event in events_plus if recent(event)}) == len(base_recent):
        fixtures["same_customer_browse_does_not_change_distinct_count"] = True

    required = {
        "duplicate_event_source_rejected", "unknown_customer_rejected", "window_end_excluded",
        "window_start_included", "removing_customer_events_changes_recent_count",
        "removing_explicit_interest_changes_stat", "same_customer_browse_does_not_change_distinct_count",
    }
    if set(fixtures) != required:
        raise AssertionError(f"independent fixture coverage mismatch: {sorted(set(fixtures) ^ required)}")
    return fixtures

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable validation output")
    args = parser.parse_args()
    try:
        result = validate_files()
        result["fixtures"] = run_independent_fixtures()
    except (AssertionError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", **result}, ensure_ascii=False, indent=None if args.json else 2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
