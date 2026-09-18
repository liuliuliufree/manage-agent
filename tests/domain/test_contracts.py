from dataclasses import FrozenInstanceError
from decimal import Decimal
import unittest

from src.domain import (
    ActorContext,
    Assumption,
    AudienceScope,
    CapabilityContext,
    CapabilityError,
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ChannelAndActor,
    Constraint,
    ErrorCategory,
    Evidence,
    EvidenceLink,
    EvidenceRole,
    EvidenceSource,
    EvidenceType,
    Goal,
    GoalLink,
    GoalRef,
    Metric,
    MissingInformation,
    ObjectScope,
    Opportunity,
    OpportunityPriority,
    Plan,
    PlanStatus,
    PlanStep,
    PriorityFactor,
    ProductOrNeedContext,
    SuccessCriterion,
    Target,
)


def performance_goal() -> Goal:
    return Goal(
        goal_id="goal-performance",
        version=1,
        original_request="本阶段达成 500W NBEV，主推 Product X 和 Product Y。",
        goal_type="performance_achievement",
        metric=Metric("nbev"),
        target=Target(Decimal("500"), "万"),
        audience_scope=AudienceScope("manageable_customers"),
        product_or_need_context=ProductOrNeedContext(products=("Product X", "Product Y")),
        channel_and_actor=ChannelAndActor("individual", "agent-1", "session"),
        success_criteria=(
            SuccessCriterion("NBEV 达到 500 万"),
        ),
    )


def context() -> CapabilityContext:
    return CapabilityContext(
        actor=ActorContext("agent-1", "individual", "authenticated_session"),
        object_scope=ObjectScope("customer", ("customer-wang",)),
    )


class GoalAndEvidenceContractTests(unittest.TestCase):
    def test_complete_performance_goal_is_generic(self) -> None:
        goal = performance_goal()
        self.assertEqual(goal.target.value, Decimal("500"))
        self.assertEqual(goal.product_or_need_context.products, ("Product X", "Product Y"))

    def test_incomplete_goal_preserves_missing_information(self) -> None:
        missing = MissingInformation("time_horizon.end_at", "No authoritative calendar", "Deadline unknown")
        goal = Goal(
            "goal-opportunities", 1, "最近有哪些客户经营机会值得关注", "opportunity_discovery",
            missing_information=(missing,),
        )
        self.assertIsNone(goal.metric)
        self.assertIsNone(goal.target)
        self.assertEqual(goal.missing_information, (missing,))

    def test_single_customer_strategy_goal_needs_no_metric(self) -> None:
        goal = Goal(
            "goal-wang", 1, "帮我看看王女士下一步怎么经营", "strategy_advice",
            audience_scope=AudienceScope("specific_customer", "customer-wang", "王女士"),
        )
        self.assertIsNone(goal.metric)
        self.assertEqual(goal.audience_scope.scope_reference, "customer-wang")

    def test_goal_revision_does_not_mutate_old_goal(self) -> None:
        original = performance_goal()
        revised = original.revise(
            original_request="目标调整为 400W，并优先老客户。",
            target=Target(Decimal("400"), "万"),
            constraints=(Constraint("prefer_existing", "优先老客户"),),
            assumptions=(Assumption("客户范围仍为可经营客户", "未另行指定", True),),
        )
        self.assertEqual((original.goal_id, original.version, original.target.value), (revised.goal_id, 1, Decimal("500")))
        self.assertEqual((revised.version, revised.target.value), (2, Decimal("400")))
        with self.assertRaises(FrozenInstanceError):
            original.version = 2

    def test_fact_requires_traceable_source(self) -> None:
        with self.assertRaises(TypeError):
            Evidence("ev-1", EvidenceType.CUSTOMER_FACT, "客户事实")  # type: ignore[call-arg]
        evidence = Evidence(
            "ev-1", EvidenceType.CUSTOMER_FACT, "客户已确认家庭结构", EvidenceSource("crm", "customer_system", "7")
        )
        self.assertEqual(evidence.source.source_id, "crm")

    def test_model_signal_remains_a_distinct_evidence_type(self) -> None:
        signal = Evidence("ev-model", EvidenceType.MODEL_SIGNAL, "需求评分 0.82", EvidenceSource("need-model", "model", "2026.1"))
        self.assertIsNot(signal.evidence_type, EvidenceType.CUSTOMER_FACT)
        self.assertFalse(hasattr(EvidenceType, "AGENT_JUDGEMENT"))


class OpportunityAndCapabilityContractTests(unittest.TestCase):
    def test_opportunity_requires_evidence(self) -> None:
        with self.assertRaises(ValueError):
            Opportunity("opp-1", GoalLink("goal-1", 1), "need_gap", "存在经营问题", ())

    def test_evidence_roles_can_coexist(self) -> None:
        opportunity = Opportunity(
            "opp-1", GoalLink("goal-1", 1), "long_term_planning_gap", "长期安排仍有讨论空间",
            (
                EvidenceLink("support", EvidenceRole.SUPPORTS),
                EvidenceLink("limit", EvidenceRole.LIMITS),
                EvidenceLink("contradiction", EvidenceRole.CONTRADICTS),
            ),
            priority=OpportunityPriority("high", factors=(PriorityFactor("need", "需求信号明确"),)),
        )
        self.assertEqual({link.role for link in opportunity.evidence_links}, set(EvidenceRole))

    def test_capability_request_allows_different_capabilities(self) -> None:
        goal_ref = GoalRef("goal-1", 1)
        strategy = CapabilityRequest("request-1", "strategy_generation", goal_ref, context())
        insight = CapabilityRequest("request-2", "directional_insight", goal_ref, context())
        self.assertNotEqual(strategy.capability_id, insight.capability_id)

    def test_capability_result_status_invariants(self) -> None:
        error = CapabilityError(ErrorCategory.TIMEOUT, "upstream_timeout", "规则服务超时", True)
        with self.assertRaises(ValueError):
            CapabilityResult("r", "validation", CapabilityStatus.FAILED)
        with self.assertRaises(ValueError):
            CapabilityResult("r", "validation", CapabilityStatus.BLOCKED)
        with self.assertRaises(ValueError):
            CapabilityResult("r", "validation", CapabilityStatus.NEED_INFORMATION)
        with self.assertRaises(ValueError):
            CapabilityResult("r", "validation", CapabilityStatus.SUCCESS, errors=(error,))
        with self.assertRaises(ValueError):
            CapabilityResult("r", "validation", CapabilityStatus.PARTIAL_SUCCESS)
        self.assertEqual(
            CapabilityResult("r", "targeting", CapabilityStatus.NO_RESULT).outputs, ()
        )
        self.assertEqual(
            CapabilityResult("r", "validation", CapabilityStatus.BLOCKED, rule_result_refs=("rule-evidence-1",)).status,
            CapabilityStatus.BLOCKED,
        )


class PlanContractTests(unittest.TestCase):
    def test_plan_allows_partial_and_repeated_capabilities(self) -> None:
        single = Plan("plan-single", 1, GoalRef("goal-1", 1), PlanStatus.ACTIVE, (PlanStep("strategy", "strategy_generation"),))
        repeated = Plan(
            "plan-repeat", 1, GoalRef("goal-1", 1), PlanStatus.ACTIVE,
            (PlanStep("insight-a", "directional_insight"), PlanStep("insight-b", "directional_insight")),
        )
        self.assertEqual(len(single.steps), 1)
        self.assertEqual(repeated.steps[0].capability_id, repeated.steps[1].capability_id)

    def test_plan_supports_parallel_dependencies(self) -> None:
        plan = Plan(
            "plan-parallel", 1, GoalRef("goal-1", 1), PlanStatus.ACTIVE,
            (
                PlanStep("insight", "directional_insight"),
                PlanStep("target-a", "customer_targeting", depends_on=("insight",)),
                PlanStep("target-b", "customer_targeting", depends_on=("insight",)),
            ),
        )
        self.assertEqual(plan.steps[1].depends_on, plan.steps[2].depends_on)

    def test_plan_rejects_unknown_dependencies_and_cycles(self) -> None:
        with self.assertRaises(ValueError):
            Plan("plan-missing", 1, GoalRef("goal-1", 1), PlanStatus.ACTIVE, (PlanStep("a", "x", depends_on=("missing",)),))
        with self.assertRaises(ValueError):
            Plan(
                "plan-cycle", 1, GoalRef("goal-1", 1), PlanStatus.ACTIVE,
                (PlanStep("a", "x", depends_on=("b",)), PlanStep("b", "y", depends_on=("a",))),
            )


if __name__ == "__main__":
    unittest.main()
