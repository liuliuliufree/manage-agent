"""Tests for deterministic management capabilities and tool exposure."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manage import (  # noqa: E402
    ANNIVERSARY_OPPORTUNITY,
    BusinessDataRepository,
    FAMILY_OPPORTUNITY,
    MEDICAL_OPPORTUNITY,
    ManageService,
)
from manage.tools import ToolContext, discover_tools  # noqa: E402


class ManageServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repository = BusinessDataRepository(ROOT / "data" / "scenarios")
        cls.service = ManageService(repository.load("demo-acts-1-3"))

    def test_business_context_keeps_boundaries_and_versions(self) -> None:
        context = self.service.get_business_context().to_dict()

        self.assertEqual(context["metadata"]["data_mode"], "synthetic")
        self.assertEqual(context["metadata"]["rule_version"], "acts-1-3-rules-v2")
        self.assertEqual(len(context["request"]["boundaries"]), 3)
        self.assertTrue(
            all(item["hard_boundary"] for item in context["request"]["boundaries"])
        )
        self.assertEqual(context["data_scope"]["customer_profile"], 120)

    def test_opportunities_are_calculated_and_ranked(self) -> None:
        analysis = self.service.analyze_opportunities().to_dict()
        counts = {
            item["opportunity_id"]: item["customer_count"]
            for item in analysis["opportunities"]
        }

        self.assertEqual(
            counts,
            {
                FAMILY_OPPORTUNITY: 86,
                MEDICAL_OPPORTUNITY: 25,
                ANNIVERSARY_OPPORTUNITY: 50,
            },
        )
        self.assertEqual(
            analysis["recommended_opportunity_id"], FAMILY_OPPORTUNITY
        )
        self.assertEqual(sum(analysis["scoring_weights"].values()), 1.0)
        self.assertGreater(
            analysis["opportunities"][0]["composite_score"],
            analysis["opportunities"][1]["composite_score"],
        )

    def test_family_opportunity_segment_matches_story(self) -> None:
        segment = self.service.segment_opportunity_customers(
            FAMILY_OPPORTUNITY
        ).to_dict()

        self.assertEqual(
            segment["funnel"],
            {
                "opportunity_customers": 86,
                "eligible_customers": 41,
                "priority_customers": 12,
            },
        )
        self.assertEqual(
            segment["exclusion_counts"],
            {
                "authorization": 14,
                "refusal": 7,
                "sensitive_status": 6,
                "frequency": 9,
                "suitability": 9,
            },
        )
        self.assertEqual(
            [item["customer_id"] for item in segment["priority_customers"]],
            [
                "C001",
                "C002",
                "C003",
                "C004",
                "C005",
                "C006",
                "C007",
                "C008",
                "C009",
                "C010",
                "C011",
                "C028",
            ],
        )
        self.assertEqual(set(segment["exclusion_samples"]), {
            "authorization",
            "refusal",
            "sensitive_status",
            "frequency",
            "suitability",
        })

    def test_customer_decision_contains_rules_and_score_evidence(self) -> None:
        c001 = self.service.explain_customer_decision(
            FAMILY_OPPORTUNITY, "C001"
        ).to_dict()
        c028 = self.service.explain_customer_decision(
            FAMILY_OPPORTUNITY, "C028"
        ).to_dict()
        excluded_id = self.service.segment_opportunity_customers(
            FAMILY_OPPORTUNITY
        ).to_dict()["exclusion_samples"]["authorization"]["customer_id"]
        excluded = self.service.explain_customer_decision(
            FAMILY_OPPORTUNITY, excluded_id
        ).to_dict()

        self.assertEqual((c001["disposition"], c001["priority_score"]), ("priority", 105))
        self.assertEqual((c028["disposition"], c028["priority_score"]), ("priority", 100))
        self.assertEqual(c001["priority_rank"], 1)
        self.assertTrue(all(item["passed"] for item in c001["hard_rule_checks"]))
        self.assertEqual(excluded["disposition"], "excluded")
        self.assertEqual(excluded["primary_reason"], "authorization")
        self.assertFalse(excluded["hard_rule_checks"][0]["passed"])
        self.assertTrue(c001["score_contributions"])
        self.assertTrue(c001["opportunity_evidence"])

    def test_repository_does_not_need_test_expectations(self) -> None:
        source = (
            ROOT
            / "data"
            / "scenarios"
            / "demo_acts_1_3_v1"
            / "source"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_dir = Path(temp_dir) / "scenario_without_expectations"
            shutil.copytree(source, scenario_dir / "source")
            service = ManageService(
                BusinessDataRepository(temp_dir).load("demo-acts-1-3")
            )

            self.assertEqual(
                service.analyze_opportunities().recommended_opportunity_id,
                FAMILY_OPPORTUNITY,
            )

    def test_tools_are_discovered_and_can_run_independently(self) -> None:
        context = ToolContext(
            BusinessDataRepository(ROOT / "data" / "scenarios")
        )
        tools = {tool.name: tool for tool in discover_tools(context)}

        self.assertEqual(
            set(tools),
            {
                "get_business_context",
                "analyze_opportunities",
                "segment_opportunity_customers",
                "explain_customer_decision",
            },
        )
        segment = tools["segment_opportunity_customers"].handler(
            {
                "data_source_id": "demo-acts-1-3",
                "opportunity_id": FAMILY_OPPORTUNITY,
            }
        )
        self.assertEqual(segment["funnel"]["priority_customers"], 12)
        self.assertEqual(context.artifacts[0]["tool_name"], "segment_opportunity_customers")


if __name__ == "__main__":
    unittest.main()
