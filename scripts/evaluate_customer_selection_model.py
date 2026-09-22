#!/usr/bin/env python3
"""Run real-model semantic evaluation against isolated human labels.

This harness is not a production runtime entry.  Only this evaluator reads
``data/evaluation``; the model receives the referenced raw customer evidence,
never expected labels.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from src.application import ArtifactStore  # noqa: E402
from src.application.customer_selection import (  # noqa: E402
    CustomerSelectionConfig,
    build_customer_selection_tools,
)
from src.application.insight_tools import InsightToolConfig  # noqa: E402
from src.model import ChatModelSettings, OpenAIChatModel  # noqa: E402


async def run() -> dict:
    labels = json.loads((ROOT / "data" / "evaluation" / "customer_selection_v2.json").read_text(encoding="utf-8"))
    if labels.get("runtime_access") != "forbidden":
        raise AssertionError("evaluation labels are not marked runtime-forbidden")
    settings = ChatModelSettings.from_env(ROOT / ".env")
    model = OpenAIChatModel(settings)
    store = ArtifactStore()
    opportunity = {
        "opportunity_id": "eval-retirement-income",
        "goal_ref": {"goal_id": "eval-goal", "version": 1},
        "opportunity_type": labels["opportunity_fixture"]["opportunity_type"],
        "problem_statement": labels["opportunity_fixture"]["problem_statement"],
        "evidence_scope": {"topic_codes": ["retirement_income"]},
        "evidence_links": [{"evidence_id": "eval-fixture", "role": "supports"}],
        "data_source": {"dataset_id": labels["dataset_id"], "version": labels["dataset_version"], "synthetic": True},
        "integration_boundary": "independent_model_evaluation_fixture",
    }
    store.put("opportunity", "eval-retirement-income", opportunity)
    config = CustomerSelectionConfig(
        insight=InsightToolConfig.from_repository(ROOT),
        actor_id="AGENT_DEMO_001",
        channel_id="individual",
    )
    query, assess = build_customer_selection_tools(config, model=model, artifact_resolver=lambda ref: store.get(ref).value)
    customer_ids = [item["customer_id"] for item in labels["labels"]]
    queried = query.handler({"customer_ids": customer_ids})
    if queried.get("status") != "ok":
        raise AssertionError(f"evidence query failed: {queried.get('error')}")
    refs = []
    for package in queried["data"]["customers"]:
        customer_id = package["customer"]["customer_id"]
        refs.append(store.put("customer_evidence", f"eval_{customer_id}", package))
    try:
        result = await assess.handler({
            "opportunity_ref": "opportunity:eval-retirement-income",
            "customer_evidence_refs": refs,
            "observed_at": "2026-09-22T00:00:00+08:00",
        })
    finally:
        await model.close()
    if result.get("status") != "ok":
        raise AssertionError(f"model assessment failed: {result.get('error')}")
    actual = {item["customer_id"]: item for item in result["data"]["assessments"]}
    checks = []
    for expected in labels["labels"]:
        item = actual.get(expected["customer_id"])
        passed = bool(item) and item.get("need_state") == expected["expected_need_state"] and item.get("suggested_tier") == expected["expected_tier"]
        cited = {
            evidence["event_id"]
            for role in ("supporting_evidence", "limiting_evidence", "contradicting_evidence")
            for evidence in (item or {}).get(role, [])
        }
        expected_evidence = set(expected["evidence_event_ids"])
        evidence_passed = expected_evidence.issubset(cited)
        checks.append({
            "customer_id": expected["customer_id"],
            "classification_passed": passed,
            "evidence_passed": evidence_passed,
            "expected": {"need_state": expected["expected_need_state"], "tier": expected["expected_tier"], "evidence": sorted(expected_evidence)},
            "actual": None if item is None else {"need_state": item.get("need_state"), "tier": item.get("suggested_tier"), "evidence": sorted(cited)},
        })
    passed = all(item["classification_passed"] and item["evidence_passed"] for item in checks)
    return {
        "status": "PASS" if passed else "FAIL",
        "evaluation_id": labels["evaluation_id"],
        "model": settings.model,
        "dataset": {"dataset_id": labels["dataset_id"], "version": labels["dataset_version"]},
        "passed": sum(item["classification_passed"] and item["evidence_passed"] for item in checks),
        "total": len(checks),
        "checks": checks,
        "note": "This measures model semantics on independent labels; it does not validate product fit or production performance.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        report = asyncio.run(run())
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())