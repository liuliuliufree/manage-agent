"""Generate and validate the deterministic mock dataset for demo acts 1-3."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping


SCENARIO_ID = "demo-acts-1-3"
SCENARIO_VERSION = "1.0.0"
RULE_VERSION = "acts-1-3-rules-v1"
DATA_DEFINITION_VERSION = "acts-1-3-data-v1"
BASELINE = datetime(2026, 9, 15, 9, 0, tzinfo=timezone(timedelta(hours=8)))
CUSTOMER_COUNT = 120
FAMILY_OPPORTUNITY_IDS = {f"C{number:03d}" for number in range(1, 87)}
ELIGIBLE_IDS = {f"C{number:03d}" for number in range(1, 42)}
PRIORITY_IDS = {f"C{number:03d}" for number in range(1, 12)} | {"C028"}

SOURCE_SCHEMAS: dict[str, tuple[str, ...]] = {
    "scenario.csv": (
        "scenario_id",
        "scenario_version",
        "baseline_at",
        "random_seed",
        "data_mode",
        "data_definition_version",
        "rule_version",
        "description",
    ),
    "business_request.csv": (
        "request_id",
        "scenario_id",
        "goal_text",
        "analysis_window",
        "desired_outcome",
        "boundaries",
        "requested_at",
        "requester_role",
    ),
    "customer_profile.csv": (
        "scenario_id",
        "customer_id",
        "age",
        "family_stage",
        "dependent_count",
        "income_band",
        "payment_capacity_band",
        "profile_updated_at",
    ),
    "family_responsibility_fact.csv": (
        "fact_id",
        "scenario_id",
        "customer_id",
        "responsibility_level",
        "required_coverage_amount",
        "source_type",
        "occurred_at",
        "valid_until",
        "authorization_id",
    ),
    "policy_coverage.csv": (
        "policy_id",
        "scenario_id",
        "customer_id",
        "coverage_type",
        "insured_amount",
        "annual_premium",
        "payment_period",
        "effective_at",
        "next_anniversary_date",
        "status",
    ),
    "authorization.csv": (
        "authorization_id",
        "scenario_id",
        "customer_id",
        "scope",
        "data_category",
        "purpose",
        "status",
        "effective_at",
        "expires_at",
        "source",
        "withdrawn_at",
    ),
    "behavior_event.csv": (
        "event_id",
        "scenario_id",
        "customer_id",
        "event_type",
        "subject",
        "occurred_at",
        "source",
        "metadata",
    ),
    "contact_event.csv": (
        "event_id",
        "scenario_id",
        "customer_id",
        "contact_type",
        "purpose",
        "occurred_at",
        "result",
        "source",
    ),
    "sensitive_status.csv": (
        "status_id",
        "scenario_id",
        "customer_id",
        "status_type",
        "started_at",
        "expected_end_at",
        "status",
        "source",
    ),
    "suitability_fact.csv": (
        "fact_id",
        "scenario_id",
        "customer_id",
        "information_complete",
        "payment_capacity_available",
        "candidate_scope_available",
        "professional_review_required",
        "evaluated_at",
        "definition_version",
    ),
    "opportunity_definition.csv": (
        "opportunity_id",
        "scenario_id",
        "name",
        "description",
        "required_signals",
        "optional_signals",
        "exclusion_conditions",
        "definition_version",
    ),
    "calculation_rule.csv": (
        "rule_id",
        "scenario_id",
        "rule_group",
        "parameter_name",
        "parameter_value",
        "value_type",
        "effective_at",
        "version",
        "description",
    ),
}

EXPECTATION_SCHEMA = (
    "scenario_id",
    "metric",
    "expected_value",
    "description",
)


def _timestamp(*, days_ago: int = 0, days_after: int = 0) -> str:
    return (BASELINE - timedelta(days=days_ago) + timedelta(days=days_after)).isoformat()


def _date_after(days: int) -> str:
    return (BASELINE.date() + timedelta(days=days)).isoformat()


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _customer_id(number: int) -> str:
    return f"C{number:03d}"


def build_tables() -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    """Build source rows and isolated test expectations in memory."""
    tables: dict[str, list[dict[str, str]]] = {
        filename: [] for filename in SOURCE_SCHEMAS
    }
    tables["scenario.csv"].append(
        {
            "scenario_id": SCENARIO_ID,
            "scenario_version": SCENARIO_VERSION,
            "baseline_at": BASELINE.isoformat(),
            "random_seed": "20260915",
            "data_mode": "synthetic",
            "data_definition_version": DATA_DEFINITION_VERSION,
            "rule_version": RULE_VERSION,
            "description": "领导演示前三幕：经营目标理解、多机会洞察与自动圈客",
        }
    )
    boundaries = [
        {
            "text": "只使用客户已授权、可用于经营的数据",
            "source": "user",
            "hard_boundary": True,
        },
        {
            "text": "强制校验营销许可、触达频次、产品适当性和人员资格",
            "source": "user",
            "hard_boundary": True,
        },
        {
            "text": "Agent 可生成策略并编排任务，具体产品推荐和销售沟通由具备资格的专业人员完成",
            "source": "user",
            "hard_boundary": True,
        },
    ]
    tables["business_request.csv"].append(
        {
            "request_id": "REQ-001",
            "scenario_id": SCENARIO_ID,
            "goal_text": "分析近期值得重点经营的加保机会。在不增加客户打扰和合规风险的前提下，优先找到真正有需求、适合经营的客户。",
            "analysis_window": "近30天",
            "desired_outcome": "发现并解释近期值得优先经营的加保机会",
            "boundaries": json.dumps(boundaries, ensure_ascii=False, separators=(",", ":")),
            "requested_at": BASELINE.isoformat(),
            "requester_role": "经营人员",
        }
    )

    for number in range(1, CUSTOMER_COUNT + 1):
        customer_id = _customer_id(number)
        in_family_opportunity = customer_id in FAMILY_OPPORTUNITY_IDS
        in_priority = customer_id in PRIORITY_IDS

        if customer_id == "C001":
            age = 35
        else:
            age = 28 + ((number * 7) % 29)
        if in_family_opportunity:
            family_stage = "raising_children" if number % 3 else "supporting_family"
            dependent_count = 1 + (number % 3)
            responsibility_level = "high"
            required_coverage_amount = 1_200_000 if in_priority else 1_000_000
        else:
            family_stage = "single" if number % 2 else "empty_nest"
            dependent_count = number % 2
            responsibility_level = "low"
            required_coverage_amount = 500_000

        payment_capacity_band = "high" if in_priority else (
            "medium" if number <= 77 else "low"
        )
        income_band = {
            "high": "300k-500k",
            "medium": "150k-300k",
            "low": "80k-150k",
        }[payment_capacity_band]
        profile_age_days = 10 + (number % 45)
        tables["customer_profile.csv"].append(
            {
                "scenario_id": SCENARIO_ID,
                "customer_id": customer_id,
                "age": str(age),
                "family_stage": family_stage,
                "dependent_count": str(dependent_count),
                "income_band": income_band,
                "payment_capacity_band": payment_capacity_band,
                "profile_updated_at": _timestamp(days_ago=profile_age_days),
            }
        )

        family_fact_age_days = 5 + (number % 55) if in_family_opportunity else 20 + (number % 50)
        data_authorization_id = f"AUTH-{customer_id}-DATA"
        tables["family_responsibility_fact.csv"].append(
            {
                "fact_id": f"FAMILY-{customer_id}",
                "scenario_id": SCENARIO_ID,
                "customer_id": customer_id,
                "responsibility_level": responsibility_level,
                "required_coverage_amount": str(required_coverage_amount),
                "source_type": "customer_update" if in_priority else "protection_assessment",
                "occurred_at": _timestamp(days_ago=family_fact_age_days),
                "valid_until": _timestamp(days_after=180 - family_fact_age_days),
                "authorization_id": data_authorization_id,
            }
        )

        if in_priority:
            insured_amount = 240_000 + (number % 4) * 20_000
        elif in_family_opportunity:
            insured_amount = 500_000 + (number % 4) * 50_000
        else:
            insured_amount = 500_000 + (number % 3) * 100_000
        next_anniversary_days = 1 + (number % 29) if 30 <= number <= 79 else 60 + (number % 120)
        tables["policy_coverage.csv"].append(
            {
                "policy_id": f"POL-{customer_id}-CI",
                "scenario_id": SCENARIO_ID,
                "customer_id": customer_id,
                "coverage_type": "critical_illness",
                "insured_amount": str(insured_amount),
                "annual_premium": str(3_600 + (number % 8) * 600),
                "payment_period": "20_years",
                "effective_at": _timestamp(days_ago=365 + number * 3),
                "next_anniversary_date": _date_after(next_anniversary_days),
                "status": "active",
            }
        )

        contact_allowed = not (42 <= number <= 55)
        tables["authorization.csv"].extend(
            [
                {
                    "authorization_id": data_authorization_id,
                    "scenario_id": SCENARIO_ID,
                    "customer_id": customer_id,
                    "scope": "data_use",
                    "data_category": "family_responsibility",
                    "purpose": "protection_analysis",
                    "status": "active",
                    "effective_at": _timestamp(days_ago=365),
                    "expires_at": _timestamp(days_after=365),
                    "source": "customer_authorization",
                    "withdrawn_at": "",
                },
                {
                    "authorization_id": f"AUTH-{customer_id}-CONTACT",
                    "scenario_id": SCENARIO_ID,
                    "customer_id": customer_id,
                    "scope": "business_contact",
                    "data_category": "",
                    "purpose": "protection_review",
                    "status": "active" if contact_allowed else "withdrawn",
                    "effective_at": _timestamp(days_ago=365),
                    "expires_at": _timestamp(days_after=365),
                    "source": "customer_authorization",
                    "withdrawn_at": "" if contact_allowed else _timestamp(days_ago=12),
                },
            ]
        )

        information_complete = not (78 <= number <= 82)
        payment_capacity_available = not (78 <= number <= 80)
        candidate_scope_available = not (83 <= number <= 86)
        tables["suitability_fact.csv"].append(
            {
                "fact_id": f"SUIT-{customer_id}",
                "scenario_id": SCENARIO_ID,
                "customer_id": customer_id,
                "information_complete": _bool(information_complete),
                "payment_capacity_available": _bool(payment_capacity_available),
                "candidate_scope_available": _bool(candidate_scope_available),
                "professional_review_required": "true",
                "evaluated_at": _timestamp(days_ago=3 + (number % 10)),
                "definition_version": "suitability-facts-v1",
            }
        )

    _add_behavior_events(tables["behavior_event.csv"])
    _add_contact_events(tables["contact_event.csv"])
    _add_sensitive_statuses(tables["sensitive_status.csv"])
    _add_opportunity_definitions(tables["opportunity_definition.csv"])
    _add_calculation_rules(tables["calculation_rule.csv"])

    expectations = [
        _expectation("customer_count", "120", "全部合成客户数"),
        _expectation("selected_opportunity_id", "OPP-FAMILY-CI-GAP", "应被推荐的机会"),
        _expectation("family_opportunity_count", "86", "第一类机会客户数"),
        _expectation("eligible_customer_count", "41", "通过经营与合规初筛人数"),
        _expectation("priority_customer_count", "12", "高优先级人数"),
        _expectation("excluded_authorization", "14", "经营授权排除人数"),
        _expectation("excluded_frequency", "9", "频控排除人数"),
        _expectation("excluded_refusal", "7", "明确拒绝排除人数"),
        _expectation("excluded_sensitive_status", "6", "敏感状态排除人数"),
        _expectation("excluded_suitability", "9", "初步适当性排除人数"),
        _expectation("c001_result", "priority", "C001 初始圈客结果"),
        _expectation("c028_result", "priority", "C028 第三幕初始圈客结果"),
    ]
    return tables, expectations


def _add_behavior_events(rows: list[dict[str, str]]) -> None:
    sequence = 1

    def add(customer_id: str, event_type: str, subject: str, days_ago: int) -> None:
        nonlocal sequence
        rows.append(
            {
                "event_id": f"BEH-{sequence:04d}",
                "scenario_id": SCENARIO_ID,
                "customer_id": customer_id,
                "event_type": event_type,
                "subject": subject,
                "occurred_at": _timestamp(days_ago=days_ago),
                "source": "synthetic_customer_activity",
                "metadata": "{}",
            }
        )
        sequence += 1

    for customer_id in sorted(PRIORITY_IDS):
        number = int(customer_id[1:])
        add(customer_id, "family_information_updated", "family_responsibility", 8 + number % 7)
        add(customer_id, "content_viewed", "critical_illness", 12 + number % 6)
        add(customer_id, "content_viewed", "critical_illness", 4 + number % 3)
        add(customer_id, "assessment_completed", "critical_illness", 3 + number % 4)
    add("C028", "consultation_started", "critical_illness", 2)

    for number in range(12, 42):
        customer_id = _customer_id(number)
        if customer_id == "C028":
            continue
        if number % 3 == 0:
            add(customer_id, "content_viewed", "critical_illness", 8 + number % 12)
        if number % 7 == 0:
            add(customer_id, "assessment_started", "critical_illness", 6 + number % 10)

    for number in range(81, 106):
        customer_id = _customer_id(number)
        add(customer_id, "content_viewed", "medical", 2 + number % 18)
        add(customer_id, "assessment_started", "medical", 1 + number % 12)


def _add_contact_events(rows: list[dict[str, str]]) -> None:
    sequence = 1

    def add(customer_id: str, days_ago: int, result: str) -> None:
        nonlocal sequence
        rows.append(
            {
                "event_id": f"CONTACT-{sequence:04d}",
                "scenario_id": SCENARIO_ID,
                "customer_id": customer_id,
                "contact_type": "marketing",
                "purpose": "protection_review",
                "occurred_at": _timestamp(days_ago=days_ago),
                "result": result,
                "source": "synthetic_contact_history",
            }
        )
        sequence += 1

    add("C001", 20, "opened")
    add("C028", 6, "no_response")
    add("C028", 3, "opened")

    for number in range(56, 65):
        customer_id = _customer_id(number)
        add(customer_id, 6, "no_response")
        add(customer_id, 4, "no_response")
        add(customer_id, 2, "opened")

    for number in range(65, 72):
        add(_customer_id(number), 1 + number % 5, "explicit_refusal")

    for number in range(15, 42, 8):
        customer_id = _customer_id(number)
        if customer_id != "C028":
            add(customer_id, 5, "opened")


def _add_sensitive_statuses(rows: list[dict[str, str]]) -> None:
    for number in range(72, 78):
        customer_id = _customer_id(number)
        status_type = "claim_in_progress" if number % 2 == 0 else "complaint_in_progress"
        rows.append(
            {
                "status_id": f"SENSITIVE-{customer_id}",
                "scenario_id": SCENARIO_ID,
                "customer_id": customer_id,
                "status_type": status_type,
                "started_at": _timestamp(days_ago=10 + number % 5),
                "expected_end_at": _timestamp(days_after=15 + number % 10),
                "status": "active",
                "source": "synthetic_sensitive_status",
            }
        )


def _add_opportunity_definitions(rows: list[dict[str, str]]) -> None:
    rows.extend(
        [
            {
                "opportunity_id": "OPP-FAMILY-CI-GAP",
                "scenario_id": SCENARIO_ID,
                "name": "家庭责任变化与重疾保障缺口",
                "description": "家庭责任信息有效且当前重疾保障低于测算所需保障",
                "required_signals": "家庭责任信息有效|数据使用授权有效|重疾保障缺口大于0",
                "optional_signals": "家庭信息近期更新|保障内容浏览|完成保障测算",
                "exclusion_conditions": "家庭责任信息过期|数据使用授权无效",
                "definition_version": "opportunity-definitions-v1",
            },
            {
                "opportunity_id": "OPP-POLICY-ANNIVERSARY",
                "scenario_id": SCENARIO_ID,
                "name": "临近保单周年的保障回顾",
                "description": "有效保单将在规则窗口内到达下一周年日",
                "required_signals": "有效保单|周年日在规则窗口内",
                "optional_signals": "存在保障缺口|家庭责任较高",
                "exclusion_conditions": "保单非有效状态",
                "definition_version": "opportunity-definitions-v1",
            },
            {
                "opportunity_id": "OPP-MEDICAL-INCOMPLETE",
                "scenario_id": SCENARIO_ID,
                "name": "主动了解医疗保障但未完成测算",
                "description": "近期主动浏览医疗保障并开始但尚未完成测算",
                "required_signals": "近期医疗保障浏览|医疗测算已开始|医疗测算未完成",
                "optional_signals": "主动咨询|多次浏览",
                "exclusion_conditions": "行为已过期|测算已经完成",
                "definition_version": "opportunity-definitions-v1",
            },
        ]
    )


def _add_calculation_rules(rows: list[dict[str, str]]) -> None:
    rule_values = [
        ("OPPORTUNITY", "family_fact_fresh_days", "180", "integer", "家庭责任事实有效天数"),
        ("OPPORTUNITY", "anniversary_window_days", "30", "integer", "保单周年机会窗口"),
        ("OPPORTUNITY", "behavior_window_days", "30", "integer", "主动行为有效窗口"),
        ("ELIGIBILITY", "frequency_window_days", "7", "integer", "营销触达频控窗口"),
        ("ELIGIBILITY", "frequency_block_count", "3", "integer", "达到该次数即暂缓经营"),
        ("PRIORITY", "priority_customer_count", "12", "integer", "高优先级客户数量"),
        ("PRIORITY", "gap_high_ratio", "0.6", "decimal", "高保障缺口比例阈值"),
        ("PRIORITY", "gap_medium_ratio", "0.4", "decimal", "中保障缺口比例阈值"),
        ("PRIORITY", "content_view_points", "10", "integer", "单次近期浏览贡献，最多两次"),
        ("PRIORITY", "assessment_completed_points", "20", "integer", "完成测算贡献"),
        ("PRIORITY", "consultation_points", "15", "integer", "主动咨询贡献"),
        ("PRIORITY", "fresh_family_fact_points", "10", "integer", "30天内家庭事实贡献"),
        ("PRIORITY", "payment_capacity_high_points", "15", "integer", "高缴费能力区间贡献"),
        ("PRIORITY", "payment_capacity_medium_points", "10", "integer", "中缴费能力区间贡献"),
        ("PRIORITY", "payment_capacity_low_points", "5", "integer", "低缴费能力区间贡献"),
        ("PRIORITY", "recent_contact_penalty", "5", "integer", "频控窗口内每次触达扣减"),
        ("OPPORTUNITY", "unit_contact_cost", "1", "decimal", "机会成本相对比较的统一单位成本"),
    ]
    for index, (group, name, value, value_type, description) in enumerate(rule_values, 1):
        rows.append(
            {
                "rule_id": f"RULE-{index:03d}",
                "scenario_id": SCENARIO_ID,
                "rule_group": group,
                "parameter_name": name,
                "parameter_value": value,
                "value_type": value_type,
                "effective_at": BASELINE.isoformat(),
                "version": RULE_VERSION,
                "description": description,
            }
        )


def _expectation(metric: str, expected_value: str, description: str) -> dict[str, str]:
    return {
        "scenario_id": SCENARIO_ID,
        "metric": metric,
        "expected_value": expected_value,
        "description": description,
    }


def write_dataset(
    output_dir: Path,
    tables: Mapping[str, list[dict[str, str]]],
    expectations: list[dict[str, str]],
) -> None:
    """Write the exact source and expectation CSV files for this scenario."""
    source_dir = output_dir / "source"
    expectation_dir = output_dir / "test_expectations"
    source_dir.mkdir(parents=True, exist_ok=True)
    expectation_dir.mkdir(parents=True, exist_ok=True)
    for filename, fieldnames in SOURCE_SCHEMAS.items():
        _write_csv(source_dir / filename, fieldnames, tables[filename])
    _write_csv(
        expectation_dir / "scenario_expectation.csv",
        EXPECTATION_SCHEMA,
        expectations,
    )


def _write_csv(
    path: Path,
    fieldnames: Iterable[str],
    rows: Iterable[Mapping[str, str]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_dataset(output_dir: Path) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    tables = {
        filename: _read_csv(output_dir / "source" / filename)
        for filename in SOURCE_SCHEMAS
    }
    expectations = _read_csv(
        output_dir / "test_expectations" / "scenario_expectation.csv"
    )
    return tables, expectations


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def validate_dataset(output_dir: Path) -> dict[str, object]:
    """Recompute the key story outcomes from CSV source facts."""
    tables, expectation_rows = read_dataset(output_dir)
    expected = {row["metric"]: row["expected_value"] for row in expectation_rows}
    customers = {row["customer_id"]: row for row in tables["customer_profile.csv"]}
    family_facts = {
        row["customer_id"]: row for row in tables["family_responsibility_fact.csv"]
    }
    critical_policies = {
        row["customer_id"]: row
        for row in tables["policy_coverage.csv"]
        if row["coverage_type"] == "critical_illness" and row["status"] == "active"
    }
    authorizations = {
        (row["customer_id"], row["scope"]): row
        for row in tables["authorization.csv"]
    }
    suitability = {
        row["customer_id"]: row for row in tables["suitability_fact.csv"]
    }
    behavior_by_customer = _group_by_customer(tables["behavior_event.csv"])
    contact_by_customer = _group_by_customer(tables["contact_event.csv"])
    sensitive_by_customer = _group_by_customer(tables["sensitive_status.csv"])

    _require(len(customers) == int(expected["customer_count"]), "customer count mismatch")
    _require(len(customers) == CUSTOMER_COUNT, "unexpected scenario customer count")
    _require(set(family_facts) == set(customers), "family facts must cover every customer")
    _require(set(critical_policies) == set(customers), "critical illness policies must cover every customer")
    _require(set(suitability) == set(customers), "suitability facts must cover every customer")
    _validate_references(tables, customers, authorizations)
    _validate_timestamps(tables)

    family_opportunity_ids = {
        customer_id
        for customer_id in customers
        if _is_family_opportunity(
            customer_id,
            family_facts,
            critical_policies,
            authorizations,
        )
    }
    _require(
        len(family_opportunity_ids) == int(expected["family_opportunity_count"]),
        "family opportunity count mismatch",
    )
    _require(family_opportunity_ids == FAMILY_OPPORTUNITY_IDS, "family opportunity members drifted")

    eligibility: dict[str, str] = {}
    exclusion_counts: Counter[str] = Counter()
    eligible_ids: set[str] = set()
    for customer_id in sorted(family_opportunity_ids):
        reason = _eligibility_reason(
            customer_id,
            authorizations,
            contact_by_customer,
            sensitive_by_customer,
            suitability,
        )
        eligibility[customer_id] = reason
        if reason == "eligible":
            eligible_ids.add(customer_id)
        else:
            exclusion_counts[reason] += 1

    _require(len(eligible_ids) == int(expected["eligible_customer_count"]), "eligible count mismatch")
    _require(eligible_ids == ELIGIBLE_IDS, "eligible customer members drifted")
    expected_exclusions = {
        "authorization": int(expected["excluded_authorization"]),
        "frequency": int(expected["excluded_frequency"]),
        "refusal": int(expected["excluded_refusal"]),
        "sensitive_status": int(expected["excluded_sensitive_status"]),
        "suitability": int(expected["excluded_suitability"]),
    }
    _require(dict(exclusion_counts) == expected_exclusions, "exclusion distribution mismatch")

    scores = {
        customer_id: _priority_score(
            customer_id,
            customers,
            family_facts,
            critical_policies,
            behavior_by_customer,
            contact_by_customer,
        )
        for customer_id in eligible_ids
    }
    priority_ids = {
        customer_id
        for customer_id, _ in sorted(
            scores.items(), key=lambda item: (-item[1], item[0])
        )[: int(expected["priority_customer_count"])]
    }
    _require(priority_ids == PRIORITY_IDS, "priority customer members drifted")
    _require("C001" in priority_ids, "C001 must be priority")
    _require("C028" in priority_ids, "C028 must be priority")
    _require(_recent_contact_count(contact_by_customer.get("C028", [])) == 2, "C028 initial contacts must remain below limit")

    anniversary_count = sum(
        _days_from_baseline(row["next_anniversary_date"]) <= 30
        for row in critical_policies.values()
    )
    medical_incomplete_count = _medical_incomplete_count(behavior_by_customer)
    _require(0 < anniversary_count < len(family_opportunity_ids), "anniversary opportunity size must be smaller")
    _require(0 < medical_incomplete_count < len(family_opportunity_ids), "medical opportunity size must be smaller")

    return {
        "customer_count": len(customers),
        "opportunities": {
            "family_ci_gap": len(family_opportunity_ids),
            "policy_anniversary": anniversary_count,
            "medical_incomplete": medical_incomplete_count,
        },
        "eligible_count": len(eligible_ids),
        "priority_count": len(priority_ids),
        "priority_ids": sorted(priority_ids),
        "exclusion_counts": dict(exclusion_counts),
        "c001_score": scores["C001"],
        "c028_score": scores["C028"],
    }


def _group_by_customer(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["customer_id"], []).append(row)
    return grouped


def _validate_references(
    tables: Mapping[str, list[dict[str, str]]],
    customers: Mapping[str, dict[str, str]],
    authorizations: Mapping[tuple[str, str], dict[str, str]],
) -> None:
    identifiers: set[str] = set()
    id_fields = {
        "family_responsibility_fact.csv": "fact_id",
        "policy_coverage.csv": "policy_id",
        "authorization.csv": "authorization_id",
        "behavior_event.csv": "event_id",
        "contact_event.csv": "event_id",
        "sensitive_status.csv": "status_id",
        "suitability_fact.csv": "fact_id",
        "opportunity_definition.csv": "opportunity_id",
        "calculation_rule.csv": "rule_id",
    }
    for filename, id_field in id_fields.items():
        for row in tables[filename]:
            identifier = f"{filename}:{row[id_field]}"
            _require(identifier not in identifiers, f"duplicate identifier: {identifier}")
            identifiers.add(identifier)
            if "customer_id" in row:
                _require(row["customer_id"] in customers, f"unknown customer: {row['customer_id']}")
    for row in tables["family_responsibility_fact.csv"]:
        authorization = authorizations.get((row["customer_id"], "data_use"))
        _require(authorization is not None, "family fact missing data authorization")
        _require(
            authorization["authorization_id"] == row["authorization_id"],
            "family fact authorization reference mismatch",
        )


def _validate_timestamps(tables: Mapping[str, list[dict[str, str]]]) -> None:
    timestamp_fields = {
        "business_request.csv": ("requested_at",),
        "customer_profile.csv": ("profile_updated_at",),
        "family_responsibility_fact.csv": ("occurred_at",),
        "policy_coverage.csv": ("effective_at",),
        "authorization.csv": ("effective_at",),
        "behavior_event.csv": ("occurred_at",),
        "contact_event.csv": ("occurred_at",),
        "sensitive_status.csv": ("started_at",),
        "suitability_fact.csv": ("evaluated_at",),
        "calculation_rule.csv": ("effective_at",),
    }
    for filename, fields in timestamp_fields.items():
        for row in tables[filename]:
            for field in fields:
                value = datetime.fromisoformat(row[field])
                _require(value <= BASELINE, f"{filename}.{field} exceeds baseline")


def _is_family_opportunity(
    customer_id: str,
    family_facts: Mapping[str, dict[str, str]],
    policies: Mapping[str, dict[str, str]],
    authorizations: Mapping[tuple[str, str], dict[str, str]],
) -> bool:
    fact = family_facts[customer_id]
    policy = policies[customer_id]
    authorization = authorizations[(customer_id, "data_use")]
    return (
        fact["responsibility_level"] in {"medium", "high"}
        and datetime.fromisoformat(fact["valid_until"]) >= BASELINE
        and authorization["status"] == "active"
        and datetime.fromisoformat(authorization["expires_at"]) >= BASELINE
        and int(fact["required_coverage_amount"]) > int(policy["insured_amount"])
    )


def _eligibility_reason(
    customer_id: str,
    authorizations: Mapping[tuple[str, str], dict[str, str]],
    contacts: Mapping[str, list[dict[str, str]]],
    sensitive_statuses: Mapping[str, list[dict[str, str]]],
    suitability: Mapping[str, dict[str, str]],
) -> str:
    authorization = authorizations[(customer_id, "business_contact")]
    if authorization["status"] != "active":
        return "authorization"
    customer_contacts = contacts.get(customer_id, [])
    if any(row["result"] in {"explicit_refusal", "unsubscribe"} for row in customer_contacts):
        return "refusal"
    if any(row["status"] == "active" for row in sensitive_statuses.get(customer_id, [])):
        return "sensitive_status"
    if _recent_contact_count(customer_contacts) >= 3:
        return "frequency"
    fact = suitability[customer_id]
    if not all(
        fact[field] == "true"
        for field in (
            "information_complete",
            "payment_capacity_available",
            "candidate_scope_available",
        )
    ):
        return "suitability"
    return "eligible"


def _recent_contact_count(rows: Iterable[dict[str, str]]) -> int:
    window_start = BASELINE - timedelta(days=7)
    return sum(
        row["contact_type"] == "marketing"
        and window_start <= datetime.fromisoformat(row["occurred_at"]) <= BASELINE
        for row in rows
    )


def _priority_score(
    customer_id: str,
    customers: Mapping[str, dict[str, str]],
    family_facts: Mapping[str, dict[str, str]],
    policies: Mapping[str, dict[str, str]],
    behaviors: Mapping[str, list[dict[str, str]]],
    contacts: Mapping[str, list[dict[str, str]]],
) -> int:
    fact = family_facts[customer_id]
    required = int(fact["required_coverage_amount"])
    insured = int(policies[customer_id]["insured_amount"])
    gap_ratio = (required - insured) / required
    if gap_ratio >= 0.6:
        score = 40
    elif gap_ratio >= 0.4:
        score = 30
    else:
        score = 20
    if datetime.fromisoformat(fact["occurred_at"]) >= BASELINE - timedelta(days=30):
        score += 10
    customer_behaviors = [
        row
        for row in behaviors.get(customer_id, [])
        if datetime.fromisoformat(row["occurred_at"]) >= BASELINE - timedelta(days=30)
    ]
    views = sum(
        row["event_type"] == "content_viewed" and row["subject"] == "critical_illness"
        for row in customer_behaviors
    )
    score += min(views, 2) * 10
    if any(
        row["event_type"] == "assessment_completed" and row["subject"] == "critical_illness"
        for row in customer_behaviors
    ):
        score += 20
    if any(row["event_type"] == "consultation_started" for row in customer_behaviors):
        score += 15
    score += {"high": 15, "medium": 10, "low": 5}[
        customers[customer_id]["payment_capacity_band"]
    ]
    score -= _recent_contact_count(contacts.get(customer_id, [])) * 5
    return score


def _days_from_baseline(value: str) -> int:
    return (date.fromisoformat(value) - BASELINE.date()).days


def _medical_incomplete_count(
    behavior_by_customer: Mapping[str, list[dict[str, str]]],
) -> int:
    count = 0
    window_start = BASELINE - timedelta(days=30)
    for rows in behavior_by_customer.values():
        recent_medical = [
            row
            for row in rows
            if row["subject"] == "medical"
            and window_start <= datetime.fromisoformat(row["occurred_at"]) <= BASELINE
        ]
        has_view = any(row["event_type"] == "content_viewed" for row in recent_medical)
        has_started = any(row["event_type"] == "assessment_started" for row in recent_medical)
        has_completed = any(row["event_type"] == "assessment_completed" for row in recent_medical)
        if has_view and has_started and not has_completed:
            count += 1
    return count


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def default_output_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "scenarios" / "demo_acts_1_3_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_dir(),
        help="Directory containing source/ and test_expectations/",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing CSV files without regenerating them",
    )
    args = parser.parse_args()
    output_dir = args.output.resolve()
    if not args.validate_only:
        tables, expectations = build_tables()
        write_dataset(output_dir, tables, expectations)
    summary = validate_dataset(output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
