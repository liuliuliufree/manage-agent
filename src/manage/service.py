"""Deterministic management-analysis capabilities."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

from .contracts import (
    BusinessContext,
    CustomerDecision,
    CustomerSummary,
    OpportunityAnalysis,
    OpportunityMetric,
    ResultMetadata,
    SegmentResult,
)
from .errors import (
    BusinessRuleError,
    CustomerNotFoundError,
    OpportunityNotFoundError,
)
from .data_repository import BusinessDataSnapshot


FAMILY_OPPORTUNITY = "OPP-FAMILY-CI-GAP"
ANNIVERSARY_OPPORTUNITY = "OPP-POLICY-ANNIVERSARY"
MEDICAL_OPPORTUNITY = "OPP-MEDICAL-INCOMPLETE"

EXCLUSION_LABELS = {
    "authorization": "经营授权无效或用途不匹配",
    "refusal": "客户已明确拒绝或退订",
    "sensitive_status": "投诉、理赔等敏感状态处理中",
    "frequency": "频控窗口内触达次数已达上限",
    "suitability": "信息不足或无法通过初步适当性判断",
    "eligible": "通过全部经营初筛硬规则",
}


class ManageService:
    """Compute opportunity and customer decisions from one immutable snapshot."""

    def __init__(self, snapshot: BusinessDataSnapshot) -> None:
        self.snapshot = snapshot
        self._customers = self._unique_by("customer_profile.csv", "customer_id")
        self._family_facts = self._unique_by(
            "family_responsibility_fact.csv", "customer_id"
        )
        self._policies_by_customer = self._group_by_customer("policy_coverage.csv")
        self._authorizations = {
            (row["customer_id"], row["scope"]): row
            for row in snapshot.tables["authorization.csv"]
        }
        self._behaviors = self._group_by_customer("behavior_event.csv")
        self._contacts = self._group_by_customer("contact_event.csv")
        self._sensitive = self._group_by_customer("sensitive_status.csv")
        self._suitability = self._unique_by("suitability_fact.csv", "customer_id")
        self._opportunity_definitions = self._unique_by(
            "opportunity_definition.csv", "opportunity_id"
        )

    def get_business_context(self) -> BusinessContext:
        rows = self.snapshot.tables["business_request.csv"]
        if len(rows) != 1:
            raise BusinessRuleError(
                "The data snapshot requires exactly one business request"
            )
        row = rows[0]
        try:
            boundaries = json.loads(row["boundaries"])
        except json.JSONDecodeError as exc:
            raise BusinessRuleError("Business request boundaries are invalid JSON") from exc
        if not isinstance(boundaries, list):
            raise BusinessRuleError("Business request boundaries must be a list")

        request = {
            "request_id": row["request_id"],
            "goal_text": row["goal_text"],
            "analysis_window": row["analysis_window"],
            "desired_outcome": row["desired_outcome"],
            "boundaries": boundaries,
            "requested_at": row["requested_at"],
            "requester_role": row["requester_role"],
            "allowed_actions": (
                "分析经营机会",
                "筛选可开展保障检视的客户",
                "生成有证据的经营解释",
            ),
            "professional_actions": (
                "具体产品适当性确认",
                "具体产品推荐",
                "销售沟通与承接",
            ),
            "stop_conditions": (
                "经营授权无效或已撤回",
                "客户明确拒绝或退订",
                "投诉、理赔等敏感状态处理中",
                "频控窗口内触达达到上限",
                "初步适当性信息不足",
            ),
            "unconfirmed_items": (),
        }
        return BusinessContext(
            metadata=self._metadata(),
            request=request,
            system_rules={
                group: dict(values)
                for group, values in sorted(self.snapshot.rules.items())
            },
            data_scope={
                filename.removesuffix(".csv"): len(rows)
                for filename, rows in sorted(self.snapshot.tables.items())
                if filename != "scenario.csv"
            },
            data_quality_notes=(
                "当前数据为合成演示数据，不具有统计代表性。",
                "预计响应、相对触达成本与机会综合分为透明演示规则指标，不是生产预测。",
                "初步适当性只支持判断是否可开展保障检视，具体产品仍需专业人员确认。",
            ),
        )

    def analyze_opportunities(self) -> OpportunityAnalysis:
        members_by_opportunity = {
            opportunity_id: self._opportunity_members(opportunity_id)
            for opportunity_id in self._opportunity_definitions
        }
        weights = {
            "size": self._float_rule("OPPORTUNITY_SCORE", "size_weight"),
            "demand": self._float_rule("OPPORTUNITY_SCORE", "demand_weight"),
            "response": self._float_rule("OPPORTUNITY_SCORE", "response_weight"),
            "confidence": self._float_rule(
                "OPPORTUNITY_SCORE", "confidence_weight"
            ),
            "risk_penalty": self._float_rule(
                "OPPORTUNITY_SCORE", "risk_penalty_weight"
            ),
            "cost_penalty": self._float_rule(
                "OPPORTUNITY_SCORE", "cost_penalty_weight"
            ),
        }
        if round(
            weights["size"]
            + weights["demand"]
            + weights["response"]
            + weights["confidence"]
            + weights["risk_penalty"]
            + weights["cost_penalty"],
            8,
        ) != 1.0:
            raise BusinessRuleError("Opportunity scoring weights must sum to 1")

        unsorted: list[dict[str, Any]] = []
        total_customers = len(self._customers)
        unit_cost = self._float_rule("OPPORTUNITY", "unit_contact_cost")
        for opportunity_id, member_ids in members_by_opportunity.items():
            definition = self._opportunity_definitions[opportunity_id]
            size_index = self._percent(len(member_ids), total_customers)
            demand = self._demand_strength(opportunity_id, member_ids)
            response = self._response_potential(opportunity_id, member_ids)
            failed = sum(
                self._eligibility(customer_id)[0] != "eligible"
                for customer_id in member_ids
            )
            risk = self._percent(failed, len(member_ids))
            confidence = self._confidence(opportunity_id, member_ids)
            relative_cost = round(len(member_ids) * unit_cost, 2)
            cost_index = self._percent(relative_cost, total_customers * unit_cost)
            composite = round(
                size_index * weights["size"]
                + demand * weights["demand"]
                + response * weights["response"]
                + confidence * weights["confidence"]
                - risk * weights["risk_penalty"]
                - cost_index * weights["cost_penalty"],
                2,
            )
            unsorted.append(
                {
                    "opportunity_id": opportunity_id,
                    "name": definition["name"],
                    "definition_version": definition["definition_version"],
                    "customer_count": len(member_ids),
                    "metrics": {
                        "size_index": size_index,
                        "demand_strength": demand,
                        "response_potential": response,
                        "risk_index": risk,
                        "confidence": confidence,
                        "relative_contact_cost": relative_cost,
                        "cost_index": cost_index,
                    },
                    "composite_score": composite,
                    "evidence": self._opportunity_evidence_summary(
                        opportunity_id, member_ids
                    ),
                    "limitations": (
                        "指标来自当前合成快照和透明规则，不代表生产预测。",
                        "机会识别只覆盖当前数据定义中的信号。",
                    ),
                }
            )

        ordered = sorted(
            unsorted,
            key=lambda item: (-item["composite_score"], item["opportunity_id"]),
        )
        opportunities = tuple(
            OpportunityMetric(
                **item,
                rank=index,
                recommended=index == 1,
            )
            for index, item in enumerate(ordered, 1)
        )
        if not opportunities:
            raise BusinessRuleError("Data source does not define any opportunities")
        return OpportunityAnalysis(
            metadata=self._metadata(),
            opportunities=opportunities,
            recommended_opportunity_id=opportunities[0].opportunity_id,
            scoring_weights=weights,
        )

    def segment_opportunity_customers(self, opportunity_id: str) -> SegmentResult:
        definition = self._definition(opportunity_id)
        member_ids = self._opportunity_members(opportunity_id)
        exclusion_counts: Counter[str] = Counter()
        exclusion_samples: dict[str, CustomerSummary] = {}
        eligible_ids: list[str] = []
        for customer_id in member_ids:
            reason, _ = self._eligibility(customer_id)
            if reason == "eligible":
                eligible_ids.append(customer_id)
            else:
                exclusion_counts[reason] += 1
                exclusion_samples.setdefault(
                    reason,
                    CustomerSummary(
                        customer_id=customer_id,
                        disposition="excluded",
                        primary_reason=reason,
                        explanation_labels=(EXCLUSION_LABELS[reason],),
                    ),
                )

        score_details = {
            customer_id: self._score_customer(customer_id, opportunity_id)
            for customer_id in eligible_ids
        }
        ranked = sorted(
            eligible_ids,
            key=lambda customer_id: (
                -score_details[customer_id][0],
                customer_id,
            ),
        )
        priority_count = self._int_rule("PRIORITY", "priority_customer_count")
        priority_customers = tuple(
            CustomerSummary(
                customer_id=customer_id,
                disposition="priority",
                primary_reason="eligible",
                priority_rank=rank,
                priority_score=score_details[customer_id][0],
                explanation_labels=tuple(
                    contribution["label"]
                    for contribution in score_details[customer_id][1]
                    if contribution["points"] > 0
                ),
            )
            for rank, customer_id in enumerate(ranked[:priority_count], 1)
        )
        return SegmentResult(
            metadata=self._metadata(),
            opportunity_id=opportunity_id,
            opportunity_name=definition["name"],
            funnel={
                "opportunity_customers": len(member_ids),
                "eligible_customers": len(eligible_ids),
                "priority_customers": len(priority_customers),
            },
            exclusion_counts={
                reason: exclusion_counts.get(reason, 0)
                for reason in EXCLUSION_LABELS
                if reason != "eligible" and exclusion_counts.get(reason, 0) > 0
            },
            priority_customers=priority_customers,
            exclusion_samples=exclusion_samples,
        )

    def explain_customer_decision(
        self,
        opportunity_id: str,
        customer_id: str,
    ) -> CustomerDecision:
        self._definition(opportunity_id)
        if customer_id not in self._customers:
            raise CustomerNotFoundError(f"Unknown customer: {customer_id}")
        members = self._opportunity_members(opportunity_id)
        if customer_id not in members:
            return CustomerDecision(
                metadata=self._metadata(),
                opportunity_id=opportunity_id,
                customer_id=customer_id,
                disposition="not_in_opportunity",
                primary_reason="opportunity_definition_not_met",
                opportunity_evidence=self._customer_opportunity_evidence(
                    customer_id, opportunity_id
                ),
                hard_rule_checks=(),
                priority_score=None,
                priority_rank=None,
                score_contributions=(),
                allowed_actions=("等待新的有效需求信号",),
                prohibited_actions=("以本机会名义开展经营触达",),
            )

        reason, checks = self._eligibility(customer_id)
        if reason != "eligible":
            return CustomerDecision(
                metadata=self._metadata(),
                opportunity_id=opportunity_id,
                customer_id=customer_id,
                disposition="excluded",
                primary_reason=reason,
                opportunity_evidence=self._customer_opportunity_evidence(
                    customer_id, opportunity_id
                ),
                hard_rule_checks=tuple(checks),
                priority_score=None,
                priority_rank=None,
                score_contributions=(),
                allowed_actions=("保留规则证据并等待阻断状态解除",),
                prohibited_actions=(
                    "开展本轮经营触达",
                    "使用优先级分覆盖硬规则结论",
                    "形成具体产品推荐",
                ),
            )

        segment = self.segment_opportunity_customers(opportunity_id)
        priority_by_id = {
            item.customer_id: item for item in segment.priority_customers
        }
        score, contributions = self._score_customer(customer_id, opportunity_id)
        priority = priority_by_id.get(customer_id)
        disposition = "priority" if priority is not None else "eligible"
        return CustomerDecision(
            metadata=self._metadata(),
            opportunity_id=opportunity_id,
            customer_id=customer_id,
            disposition=disposition,
            primary_reason="eligible",
            opportunity_evidence=self._customer_opportunity_evidence(
                customer_id, opportunity_id
            ),
            hard_rule_checks=tuple(checks),
            priority_score=score,
            priority_rank=priority.priority_rank if priority else None,
            score_contributions=tuple(contributions),
            allowed_actions=(
                "开展保障检视",
                "由具备资格的专业人员进一步确认具体需求与适当性",
            ),
            prohibited_actions=(
                "直接认定客户适合某一具体产品",
                "未经执行前复检直接触达",
            ),
        )

    def _opportunity_members(self, opportunity_id: str) -> list[str]:
        self._definition(opportunity_id)
        if opportunity_id == FAMILY_OPPORTUNITY:
            return [
                customer_id
                for customer_id in sorted(self._customers)
                if self._is_family_opportunity(customer_id)
            ]
        if opportunity_id == ANNIVERSARY_OPPORTUNITY:
            days = self._int_rule("OPPORTUNITY", "anniversary_window_days")
            end = self.snapshot.baseline.date() + timedelta(days=days)
            return [
                customer_id
                for customer_id in sorted(self._customers)
                if any(
                    row["status"] == "active"
                    and self.snapshot.baseline.date()
                    <= date.fromisoformat(row["next_anniversary_date"])
                    <= end
                    for row in self._policies_by_customer.get(customer_id, [])
                )
            ]
        if opportunity_id == MEDICAL_OPPORTUNITY:
            window_start = self.snapshot.baseline - timedelta(
                days=self._int_rule("OPPORTUNITY", "behavior_window_days")
            )
            members: list[str] = []
            for customer_id in sorted(self._customers):
                rows = [
                    row
                    for row in self._behaviors.get(customer_id, [])
                    if row["subject"] == "medical"
                    and window_start
                    <= datetime.fromisoformat(row["occurred_at"])
                    <= self.snapshot.baseline
                ]
                event_types = {row["event_type"] for row in rows}
                if (
                    "content_viewed" in event_types
                    and "assessment_started" in event_types
                    and "assessment_completed" not in event_types
                ):
                    members.append(customer_id)
            return members
        raise OpportunityNotFoundError(
            f"Opportunity has no implemented definition: {opportunity_id}"
        )

    def _is_family_opportunity(self, customer_id: str) -> bool:
        fact = self._family_facts.get(customer_id)
        policy = self._critical_policy(customer_id)
        authorization = self._authorizations.get((customer_id, "data_use"))
        if fact is None or policy is None or authorization is None:
            return False
        fresh_days = self._int_rule("OPPORTUNITY", "family_fact_fresh_days")
        occurred_at = datetime.fromisoformat(fact["occurred_at"])
        return (
            fact["responsibility_level"] in {"medium", "high"}
            and occurred_at
            >= self.snapshot.baseline - timedelta(days=fresh_days)
            and datetime.fromisoformat(fact["valid_until"]) >= self.snapshot.baseline
            and self._authorization_active(authorization)
            and int(fact["required_coverage_amount"])
            > int(policy["insured_amount"])
        )

    def _eligibility(
        self, customer_id: str
    ) -> tuple[str, list[dict[str, Any]]]:
        contact_authorization = self._authorizations.get(
            (customer_id, "business_contact")
        )
        authorization_passed = (
            contact_authorization is not None
            and self._authorization_active(contact_authorization)
            and contact_authorization.get("purpose") == "protection_review"
        )
        contacts = self._contacts.get(customer_id, [])
        refusals = [
            row
            for row in contacts
            if row["result"] in {"explicit_refusal", "unsubscribe"}
        ]
        active_sensitive = [
            row
            for row in self._sensitive.get(customer_id, [])
            if row["status"] == "active"
        ]
        recent_contact_count = self._recent_contact_count(contacts)
        frequency_limit = self._int_rule("ELIGIBILITY", "frequency_block_count")
        suitability = self._suitability.get(customer_id)
        suitability_passed = suitability is not None and all(
            suitability[field] == "true"
            for field in (
                "information_complete",
                "payment_capacity_available",
                "candidate_scope_available",
            )
        )
        checks = [
            {
                "rule": "authorization",
                "passed": authorization_passed,
                "evidence_refs": (
                    (contact_authorization["authorization_id"],)
                    if contact_authorization
                    else ()
                ),
            },
            {
                "rule": "refusal",
                "passed": not refusals,
                "evidence_refs": tuple(row["event_id"] for row in refusals),
            },
            {
                "rule": "sensitive_status",
                "passed": not active_sensitive,
                "evidence_refs": tuple(
                    row["status_id"] for row in active_sensitive
                ),
            },
            {
                "rule": "frequency",
                "passed": recent_contact_count < frequency_limit,
                "observed": recent_contact_count,
                "limit": frequency_limit,
                "window_days": self._int_rule(
                    "ELIGIBILITY", "frequency_window_days"
                ),
                "evidence_refs": tuple(
                    row["event_id"]
                    for row in contacts
                    if self._is_recent_marketing_contact(row)
                ),
            },
            {
                "rule": "suitability",
                "passed": suitability_passed,
                "evidence_refs": (
                    (suitability["fact_id"],) if suitability else ()
                ),
            },
        ]
        for reason in (
            "authorization",
            "refusal",
            "sensitive_status",
            "frequency",
            "suitability",
        ):
            check = next(item for item in checks if item["rule"] == reason)
            if not check["passed"]:
                return reason, checks
        return "eligible", checks

    def _score_customer(
        self,
        customer_id: str,
        opportunity_id: str,
    ) -> tuple[int, list[dict[str, Any]]]:
        fact = self._family_facts[customer_id]
        policy = self._critical_policy(customer_id)
        if policy is None:
            raise BusinessRuleError(
                f"Customer {customer_id} has no active critical illness policy"
            )
        required = int(fact["required_coverage_amount"])
        insured = int(policy["insured_amount"])
        gap_ratio = (required - insured) / required
        high_threshold = self._float_rule("PRIORITY", "gap_high_ratio")
        medium_threshold = self._float_rule("PRIORITY", "gap_medium_ratio")
        if gap_ratio >= high_threshold:
            gap_points = self._int_rule("PRIORITY", "gap_high_points")
        elif gap_ratio >= medium_threshold:
            gap_points = self._int_rule("PRIORITY", "gap_medium_points")
        else:
            gap_points = self._int_rule("PRIORITY", "gap_low_points")
        contributions: list[dict[str, Any]] = [
            {
                "factor": "coverage_gap",
                "points": gap_points,
                "label": f"保障缺口比例 {gap_ratio:.0%}",
                "evidence_refs": (fact["fact_id"], policy["policy_id"]),
            }
        ]

        fresh_days = self._int_rule("PRIORITY", "fresh_family_fact_days")
        fresh = datetime.fromisoformat(fact["occurred_at"]) >= (
            self.snapshot.baseline - timedelta(days=fresh_days)
        )
        contributions.append(
            {
                "factor": "fresh_family_fact",
                "points": self._int_rule("PRIORITY", "fresh_family_fact_points")
                if fresh
                else 0,
                "label": "近期家庭责任事实" if fresh else "家庭责任事实不在近期窗口",
                "evidence_refs": (fact["fact_id"],),
            }
        )

        behavior_window = self.snapshot.baseline - timedelta(
            days=self._int_rule("OPPORTUNITY", "behavior_window_days")
        )
        subject = "medical" if opportunity_id == MEDICAL_OPPORTUNITY else "critical_illness"
        behaviors = [
            row
            for row in self._behaviors.get(customer_id, [])
            if row["subject"] == subject
            and datetime.fromisoformat(row["occurred_at"]) >= behavior_window
        ]
        views = [row for row in behaviors if row["event_type"] == "content_viewed"]
        capped_views = min(
            len(views), self._int_rule("PRIORITY", "max_scored_content_views")
        )
        contributions.append(
            {
                "factor": "content_views",
                "points": capped_views
                * self._int_rule("PRIORITY", "content_view_points"),
                "label": f"近期相关内容浏览 {len(views)} 次",
                "evidence_refs": tuple(row["event_id"] for row in views),
            }
        )
        completed = [
            row for row in behaviors if row["event_type"] == "assessment_completed"
        ]
        contributions.append(
            {
                "factor": "assessment_completed",
                "points": self._int_rule(
                    "PRIORITY", "assessment_completed_points"
                )
                if completed
                else 0,
                "label": "近期完成保障测算" if completed else "近期未完成保障测算",
                "evidence_refs": tuple(row["event_id"] for row in completed),
            }
        )
        consultations = [
            row for row in behaviors if row["event_type"] == "consultation_started"
        ]
        contributions.append(
            {
                "factor": "consultation",
                "points": self._int_rule("PRIORITY", "consultation_points")
                if consultations
                else 0,
                "label": "近期主动咨询" if consultations else "近期无主动咨询",
                "evidence_refs": tuple(row["event_id"] for row in consultations),
            }
        )
        band = self._customers[customer_id]["payment_capacity_band"]
        contributions.append(
            {
                "factor": "payment_capacity",
                "points": self._int_rule(
                    "PRIORITY", f"payment_capacity_{band}_points"
                ),
                "label": f"持续缴费能力区间：{band}",
                "evidence_refs": (self._suitability[customer_id]["fact_id"],),
            }
        )
        contact_count = self._recent_contact_count(
            self._contacts.get(customer_id, [])
        )
        contributions.append(
            {
                "factor": "recent_contact_penalty",
                "points": -contact_count
                * self._int_rule("PRIORITY", "recent_contact_penalty"),
                "label": f"频控窗口内营销触达 {contact_count} 次",
                "evidence_refs": tuple(
                    row["event_id"]
                    for row in self._contacts.get(customer_id, [])
                    if self._is_recent_marketing_contact(row)
                ),
            }
        )
        return sum(item["points"] for item in contributions), contributions

    def _demand_strength(self, opportunity_id: str, member_ids: list[str]) -> float:
        if not member_ids:
            return 0.0
        if opportunity_id == MEDICAL_OPPORTUNITY:
            values = []
            for customer_id in member_ids:
                rows = [
                    row
                    for row in self._behaviors.get(customer_id, [])
                    if row["subject"] == "medical"
                ]
                views = sum(row["event_type"] == "content_viewed" for row in rows)
                consultation = any(
                    row["event_type"] == "consultation_started" for row in rows
                )
                values.append(min(100.0, 75.0 + min(views, 2) * 7.5 + consultation * 10.0))
            return round(sum(values) / len(values), 2)

        values = []
        for customer_id in member_ids:
            fact = self._family_facts.get(customer_id)
            policy = self._critical_policy(customer_id)
            if fact is None or policy is None:
                values.append(0.0)
                continue
            required = int(fact["required_coverage_amount"])
            gap_ratio = max(0.0, (required - int(policy["insured_amount"])) / required)
            responsibility_bonus = {
                "high": 20.0,
                "medium": 10.0,
                "low": 0.0,
            }.get(fact["responsibility_level"], 0.0)
            values.append(min(100.0, gap_ratio * 100.0 + responsibility_bonus))
        return round(sum(values) / len(values), 2)

    def _response_potential(
        self, opportunity_id: str, member_ids: list[str]
    ) -> float:
        if not member_ids:
            return 0.0
        subject = "medical" if opportunity_id == MEDICAL_OPPORTUNITY else "critical_illness"
        window_start = self.snapshot.baseline - timedelta(
            days=self._int_rule("OPPORTUNITY", "behavior_window_days")
        )
        values = []
        for customer_id in member_ids:
            rows = [
                row
                for row in self._behaviors.get(customer_id, [])
                if row["subject"] == subject
                and datetime.fromisoformat(row["occurred_at"]) >= window_start
            ]
            views = min(
                sum(row["event_type"] == "content_viewed" for row in rows), 2
            )
            started = any(row["event_type"] == "assessment_started" for row in rows)
            completed = any(
                row["event_type"] == "assessment_completed" for row in rows
            )
            consultation = any(
                row["event_type"] == "consultation_started" for row in rows
            )
            score = views * 15 + started * 20 + completed * 35 + consultation * 30
            if opportunity_id == FAMILY_OPPORTUNITY:
                score += 15 * any(
                    row["event_type"] == "family_information_updated"
                    for row in self._behaviors.get(customer_id, [])
                    if datetime.fromisoformat(row["occurred_at"]) >= window_start
                )
            values.append(min(100.0, float(score)))
        return round(sum(values) / len(values), 2)

    def _confidence(self, opportunity_id: str, member_ids: list[str]) -> float:
        if not member_ids:
            return 0.0
        complete = 0
        for customer_id in member_ids:
            if opportunity_id == FAMILY_OPPORTUNITY:
                ok = (
                    customer_id in self._family_facts
                    and self._critical_policy(customer_id) is not None
                    and (customer_id, "data_use") in self._authorizations
                )
            elif opportunity_id == ANNIVERSARY_OPPORTUNITY:
                ok = self._critical_policy(customer_id) is not None
            else:
                ok = bool(self._behaviors.get(customer_id))
            complete += ok
        return self._percent(complete, len(member_ids))

    def _opportunity_evidence_summary(
        self, opportunity_id: str, member_ids: list[str]
    ) -> tuple[str, ...]:
        if opportunity_id == FAMILY_OPPORTUNITY:
            return (
                f"{len(member_ids)} 名客户同时具备有效家庭责任事实、数据使用授权和重疾保障缺口。",
                "保障缺口由所需保障额度减去当前有效保障额度计算。",
            )
        if opportunity_id == ANNIVERSARY_OPPORTUNITY:
            return (
                f"{len(member_ids)} 名客户的有效保单在周年窗口内。",
                "周年窗口来自当前规则快照。",
            )
        return (
            f"{len(member_ids)} 名客户近期浏览医疗保障并开始但未完成测算。",
            "行为信号均发生在当前规则定义的有效窗口内。",
        )

    def _customer_opportunity_evidence(
        self, customer_id: str, opportunity_id: str
    ) -> tuple[dict[str, Any], ...]:
        if opportunity_id == FAMILY_OPPORTUNITY:
            fact = self._family_facts.get(customer_id)
            policy = self._critical_policy(customer_id)
            authorization = self._authorizations.get((customer_id, "data_use"))
            return (
                {
                    "signal": "family_responsibility",
                    "matched": fact is not None,
                    "evidence_ref": fact["fact_id"] if fact else None,
                    "occurred_at": fact["occurred_at"] if fact else None,
                },
                {
                    "signal": "data_use_authorization",
                    "matched": authorization is not None
                    and self._authorization_active(authorization),
                    "evidence_ref": authorization["authorization_id"]
                    if authorization
                    else None,
                },
                {
                    "signal": "critical_illness_coverage_gap",
                    "matched": fact is not None
                    and policy is not None
                    and int(fact["required_coverage_amount"])
                    > int(policy["insured_amount"]),
                    "required_coverage_amount": int(fact["required_coverage_amount"])
                    if fact
                    else None,
                    "insured_amount": int(policy["insured_amount"])
                    if policy
                    else None,
                    "evidence_refs": tuple(
                        value
                        for value in (
                            fact["fact_id"] if fact else None,
                            policy["policy_id"] if policy else None,
                        )
                        if value is not None
                    ),
                },
            )
        if opportunity_id == ANNIVERSARY_OPPORTUNITY:
            policies = [
                row
                for row in self._policies_by_customer.get(customer_id, [])
                if row["status"] == "active"
            ]
            return tuple(
                {
                    "signal": "policy_anniversary",
                    "matched": True,
                    "evidence_ref": row["policy_id"],
                    "next_anniversary_date": row["next_anniversary_date"],
                }
                for row in policies
            )
        rows = [
            row
            for row in self._behaviors.get(customer_id, [])
            if row["subject"] == "medical"
        ]
        return tuple(
            {
                "signal": row["event_type"],
                "matched": True,
                "evidence_ref": row["event_id"],
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        )

    def _authorization_active(self, row: Mapping[str, str]) -> bool:
        return (
            row["status"] == "active"
            and datetime.fromisoformat(row["effective_at"]) <= self.snapshot.baseline
            and datetime.fromisoformat(row["expires_at"]) >= self.snapshot.baseline
            and not row.get("withdrawn_at")
        )

    def _recent_contact_count(self, rows: Iterable[dict[str, str]]) -> int:
        return sum(self._is_recent_marketing_contact(row) for row in rows)

    def _is_recent_marketing_contact(self, row: Mapping[str, str]) -> bool:
        window_start = self.snapshot.baseline - timedelta(
            days=self._int_rule("ELIGIBILITY", "frequency_window_days")
        )
        occurred_at = datetime.fromisoformat(row["occurred_at"])
        return (
            row["contact_type"] == "marketing"
            and window_start <= occurred_at <= self.snapshot.baseline
        )

    def _critical_policy(self, customer_id: str) -> dict[str, str] | None:
        return next(
            (
                row
                for row in self._policies_by_customer.get(customer_id, [])
                if row["coverage_type"] == "critical_illness"
                and row["status"] == "active"
            ),
            None,
        )

    def _definition(self, opportunity_id: str) -> dict[str, str]:
        definition = self._opportunity_definitions.get(opportunity_id)
        if definition is None:
            raise OpportunityNotFoundError(f"Unknown opportunity: {opportunity_id}")
        return definition

    def _metadata(self) -> ResultMetadata:
        metadata = self.snapshot.metadata
        return ResultMetadata(
            data_source_id=metadata["scenario_id"],
            data_source_version=metadata["scenario_version"],
            baseline_at=metadata["baseline_at"],
            data_mode=metadata["data_mode"],
            data_definition_version=metadata["data_definition_version"],
            rule_version=metadata["rule_version"],
        )

    def _unique_by(self, filename: str, key: str) -> dict[str, dict[str, str]]:
        return {row[key]: row for row in self.snapshot.tables[filename]}

    def _group_by_customer(self, filename: str) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in self.snapshot.tables[filename]:
            grouped.setdefault(row["customer_id"], []).append(row)
        return grouped

    def _int_rule(self, group: str, name: str) -> int:
        value = self._rule(group, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise BusinessRuleError(f"Rule {group}.{name} must be an integer")
        return value

    def _float_rule(self, group: str, name: str) -> float:
        value = self._rule(group, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BusinessRuleError(f"Rule {group}.{name} must be numeric")
        return float(value)

    def _rule(self, group: str, name: str) -> int | float | str:
        try:
            return self.snapshot.rules[group][name]
        except KeyError as exc:
            raise BusinessRuleError(f"Missing business rule: {group}.{name}") from exc

    @staticmethod
    def _percent(numerator: float, denominator: float) -> float:
        if denominator == 0:
            return 0.0
        return round(numerator / denominator * 100.0, 2)
