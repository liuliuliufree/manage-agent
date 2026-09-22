import unittest

from src.application import (
    ArtifactStore,
    BusinessAgent,
    BusinessAgentStatus,
    CapabilityExecutor,
    CapabilityIO,
    GoalParseResult,
    GoalParseStatus,
    PlanningUnavailableError,
)
from src.domain import (
    CapabilityError,
    CapabilityOutput,
    CapabilityResult,
    CapabilityStatus,
    ChannelAndActor,
    ErrorCategory,
    Goal,
    GoalRef,
    MissingInformation,
    Plan,
    PlanStatus,
    PlanStep,
)


def goal(*, missing=()):
    return Goal(
        goal_id="goal-1",
        version=1,
        original_request="虚构测试目标",
        goal_type="opportunity_discovery",
        channel_and_actor=ChannelAndActor("individual", "agent-1", "demo_runtime"),
        missing_information=tuple(missing),
    )


def plan(*steps):
    return Plan(
        plan_id="plan-1",
        version=1,
        goal_ref=GoalRef("goal-1", 1),
        status=PlanStatus.ACTIVE,
        steps=tuple(steps),
    )


class ParserStub:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def parse(self, **kwargs):
        self.calls += 1
        return self.result


class PlannerStub:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def plan(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def parser_success(parsed_goal=None):
    return ParserStub(
        GoalParseResult(
            GoalParseStatus.SUCCESS,
            goal=parsed_goal or goal(),
        )
    )


CATALOG = {
    "insight": {"description": "synthetic insight"},
    "targeting": {"description": "synthetic targeting"},
    "strategy": {"description": "synthetic strategy"},
    "not_installed": {"description": "not installed"},
}
IO = {
    "insight": CapabilityIO(output_types=("opportunity",)),
    "targeting": CapabilityIO(
        required_inputs=("opportunity",), output_types=("customer_set",)
    ),
    "strategy": CapabilityIO(
        required_inputs=("customer_set",), output_types=("strategy",)
    ),
}


class ArtifactFlowIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def run_chain(self, segment):
        store = ArtifactStore()
        reads = []

        def insight(request):
            store.put("opportunity", "opp-1", {"segment": segment})
            return CapabilityResult(
                request.request_id,
                request.capability_id,
                CapabilityStatus.SUCCESS,
                outputs=(CapabilityOutput("opp-1", "opportunity", "synthetic"),),
            )

        def targeting(request):
            opportunity = store.get(request.input_refs[0]).value
            reads.append(("targeting", opportunity["segment"]))
            customers = (
                ["fictional-retirement-customer"]
                if opportunity["segment"] == "retirement"
                else ["fictional-family-customer"]
            )
            store.put("customer_set", "customers-1", {"customers": customers})
            return CapabilityResult(
                request.request_id,
                request.capability_id,
                CapabilityStatus.SUCCESS,
                outputs=(CapabilityOutput("customers-1", "customer_set", "synthetic"),),
            )

        def strategy(request):
            customers = store.get(request.input_refs[0]).value["customers"]
            reads.append(("strategy", tuple(customers)))
            store.put("strategy", "strategy-1", {"for_customers": customers})
            return CapabilityResult(
                request.request_id,
                request.capability_id,
                CapabilityStatus.SUCCESS,
                outputs=(CapabilityOutput("strategy-1", "strategy", "synthetic"),),
            )

        steps = (
            PlanStep("inspect", "insight"),
            PlanStep("target", "targeting", ("inspect",)),
            PlanStep("write", "strategy", ("target",)),
        )
        planner = PlannerStub(plan(*steps))
        agent = BusinessAgent(
            goal_parser=parser_success(),
            planner=planner,
            capability_executor=CapabilityExecutor(
                {"insight": insight, "targeting": targeting, "strategy": strategy}
            ),
            capability_io=IO,
            capability_catalog=CATALOG,
        )
        response = await agent.handle(user_request="虚构测试目标", artifact_store=store)
        return response, store, reads, planner

    async def test_three_steps_read_real_upstream_objects_and_content_changes_downstream(self):
        retirement, store_a, reads_a, planner_a = await self.run_chain("retirement")
        family, store_b, reads_b, planner_b = await self.run_chain("family")
        self.assertIs(retirement.status, BusinessAgentStatus.COMPLETED)
        self.assertIs(family.status, BusinessAgentStatus.COMPLETED)
        self.assertEqual(
            store_a.get("strategy:strategy-1").value["for_customers"],
            ["fictional-retirement-customer"],
        )
        self.assertEqual(
            store_b.get("strategy:strategy-1").value["for_customers"],
            ["fictional-family-customer"],
        )
        self.assertNotEqual(reads_a, reads_b)
        self.assertEqual(len(planner_a.calls), 1)
        self.assertEqual(len(planner_b.calls), 1)
        self.assertEqual(retirement.plan.version, 1)

    async def test_initial_opportunity_allows_targeting_to_skip_insight(self):
        store = ArtifactStore()
        store.put("opportunity", "initial-opp", {"segment": "synthetic-initial"})
        seen = []

        def targeting(request):
            seen.append(store.get(request.input_refs[0]).value["segment"])
            store.put("customer_set", "set-1", {"customers": ["fictional-customer"]})
            return CapabilityResult(
                request.request_id,
                request.capability_id,
                CapabilityStatus.SUCCESS,
                outputs=(CapabilityOutput("set-1", "customer_set", "synthetic"),),
            )

        agent = BusinessAgent(
            goal_parser=parser_success(),
            planner=PlannerStub(plan(PlanStep("target", "targeting"))),
            capability_executor=CapabilityExecutor({"targeting": targeting}),
            capability_io={"targeting": IO["targeting"]},
            capability_catalog=CATALOG,
        )
        response = await agent.handle(
            user_request="虚构测试目标",
            existing_context={"opportunity_refs": ["initial-opp"]},
            artifact_store=store,
        )
        self.assertIs(response.status, BusinessAgentStatus.COMPLETED)
        self.assertEqual(seen, ["synthetic-initial"])
        self.assertEqual(response.plan.steps[0].capability_id, "targeting")

    async def test_missing_required_input_clarifies_without_handler_or_second_plan(self):
        calls = []

        def targeting(request):
            calls.append(request)
            raise AssertionError("must not execute")

        planner = PlannerStub(plan(PlanStep("target", "targeting")))
        agent = BusinessAgent(
            goal_parser=parser_success(),
            planner=planner,
            capability_executor=CapabilityExecutor({"targeting": targeting}),
            capability_io={"targeting": IO["targeting"]},
            capability_catalog=CATALOG,
        )
        response = await agent.handle(user_request="虚构测试目标")
        self.assertIs(response.status, BusinessAgentStatus.CLARIFICATION_REQUIRED)
        self.assertEqual(response.missing_information[0].field, "input_refs.opportunity")
        self.assertEqual(calls, [])
        self.assertEqual(response.execution_context.step_results, {})
        self.assertEqual(len(planner.calls), 1)
        self.assertEqual(response.plan.version, 1)

    async def test_no_result_partial_blocked_and_failed_stop_without_replan(self):
        cases = [
            (CapabilityStatus.NO_RESULT, {}),
            (CapabilityStatus.PARTIAL_SUCCESS, {"limitations": ("synthetic",)}),
            (CapabilityStatus.BLOCKED, {"rule_result_refs": ("rule_result:synthetic",)}),
            (
                CapabilityStatus.FAILED,
                {"errors": (CapabilityError(ErrorCategory.INTERNAL, "synthetic", "failed"),)},
            ),
        ]
        for status, kwargs in cases:
            with self.subTest(status=status):
                downstream_calls = []

                def first(request, current=status, fields=kwargs):
                    return CapabilityResult(
                        request.request_id,
                        request.capability_id,
                        current,
                        **fields,
                    )

                def downstream(request):
                    downstream_calls.append(request)
                    raise AssertionError("must not execute")

                run_plan = plan(
                    PlanStep("first", "insight"),
                    PlanStep("second", "targeting", ("first",)),
                )
                planner = PlannerStub(run_plan)
                agent = BusinessAgent(
                    goal_parser=parser_success(),
                    planner=planner,
                    capability_executor=CapabilityExecutor(
                        {"insight": first, "targeting": downstream}
                    ),
                    capability_io={"insight": IO["insight"], "targeting": IO["targeting"]},
                    capability_catalog=CATALOG,
                )
                response = await agent.handle(user_request="虚构测试目标")
                self.assertIs(response.status, BusinessAgentStatus.STOPPED)
                self.assertIs(response.last_result.status, status)
                self.assertEqual(downstream_calls, [])
                self.assertEqual(len(planner.calls), 1)
                self.assertEqual(response.plan.version, 1)
                self.assertFalse(hasattr(planner, "replan"))
                if status is CapabilityStatus.BLOCKED:
                    self.assertEqual(
                        response.last_result.rule_result_refs,
                        ("rule_result:synthetic",),
                    )

    async def test_need_information_preserves_structured_missing_and_stops(self):
        missing = MissingInformation("business_input", "synthetic missing", "blocks", True)

        def handler(request):
            return CapabilityResult(
                request.request_id,
                request.capability_id,
                CapabilityStatus.NEED_INFORMATION,
                missing_information=(missing,),
            )

        agent = BusinessAgent(
            goal_parser=parser_success(),
            planner=PlannerStub(plan(PlanStep("one", "insight"))),
            capability_executor=CapabilityExecutor({"insight": handler}),
            capability_io={"insight": IO["insight"]},
            capability_catalog=CATALOG,
        )
        response = await agent.handle(user_request="虚构测试目标")
        self.assertIs(response.status, BusinessAgentStatus.CLARIFICATION_REQUIRED)
        self.assertEqual(response.missing_information, (missing,))

    async def test_catalog_is_intersection_of_description_and_callable_handlers(self):
        planner = PlannerStub(plan(PlanStep("one", "insight")))

        def handler(request):
            return CapabilityResult(
                request.request_id, request.capability_id, CapabilityStatus.SUCCESS
            )

        agent = BusinessAgent(
            goal_parser=parser_success(),
            planner=planner,
            capability_executor=CapabilityExecutor(
                {"insight": handler, "handler_only": handler}
            ),
            capability_io={"insight": IO["insight"]},
            capability_catalog=CATALOG,
        )
        response = await agent.handle(user_request="虚构测试目标")
        self.assertIs(response.status, BusinessAgentStatus.COMPLETED)
        sent = planner.calls[0]["capability_catalog"]
        self.assertEqual(set(sent), {"insight"})

    async def test_empty_intersection_stops_without_planner_model_or_handler(self):
        planner = PlannerStub(error=PlanningUnavailableError())
        agent = BusinessAgent(
            goal_parser=parser_success(),
            planner=planner,
            capability_executor=CapabilityExecutor({}),
            capability_io={},
            capability_catalog=CATALOG,
        )
        response = await agent.handle(user_request="虚构测试目标")
        self.assertIs(response.status, BusinessAgentStatus.STOPPED)
        self.assertEqual(planner.calls[0]["capability_catalog"], {})

    async def test_parser_gates_planner_for_clarification_failure_and_contradiction(self):
        missing = MissingInformation("metric", "missing", "blocks", True)
        cases = [
            GoalParseResult(
                GoalParseStatus.CLARIFICATION_REQUIRED,
                missing_information=(missing,),
                clarification_question="complete request",
            ),
            GoalParseResult(GoalParseStatus.TECHNICAL_FAILURE, error="MODEL_CALL_FAILED"),
            GoalParseResult(GoalParseStatus.SUCCESS, goal=goal(missing=(missing,))),
            GoalParseResult(GoalParseStatus.SUCCESS, goal=None),
        ]
        for parse_result in cases:
            with self.subTest(status=parse_result.status, goal=parse_result.goal):
                planner = PlannerStub(plan(PlanStep("one", "insight")))
                agent = BusinessAgent(
                    goal_parser=ParserStub(parse_result),
                    planner=planner,
                    capability_executor=CapabilityExecutor({}),
                    capability_io={},
                    capability_catalog=CATALOG,
                )
                response = await agent.handle(user_request="虚构测试目标")
                self.assertIn(
                    response.status,
                    {BusinessAgentStatus.CLARIFICATION_REQUIRED, BusinessAgentStatus.FAILED},
                )
                self.assertEqual(planner.calls, [])

    async def test_store_reuse_and_new_run_isolation(self):
        run_plan = plan(PlanStep("one", "insight"))

        def make_agent(store, output_id):
            def handler(request):
                store.put("opportunity", output_id, {"run": output_id})
                return CapabilityResult(
                    request.request_id,
                    request.capability_id,
                    CapabilityStatus.SUCCESS,
                    outputs=(CapabilityOutput(output_id, "opportunity", "synthetic"),),
                )

            return BusinessAgent(
                goal_parser=parser_success(),
                planner=PlannerStub(run_plan),
                capability_executor=CapabilityExecutor({"insight": handler}),
                capability_io={"insight": IO["insight"]},
                capability_catalog=CATALOG,
            )

        first_store = ArtifactStore()
        first = await make_agent(first_store, "run-1").handle(
            user_request="虚构测试目标", artifact_store=first_store
        )
        self.assertIs(first.status, BusinessAgentStatus.COMPLETED)
        reused = await make_agent(first_store, "run-2").handle(
            user_request="虚构测试目标", artifact_store=first_store
        )
        self.assertIs(reused.status, BusinessAgentStatus.FAILED)
        self.assertEqual(reused.error, "ARTIFACT_STORE_REUSED")

        second_store = ArtifactStore()
        second = await make_agent(second_store, "run-2").handle(
            user_request="虚构测试目标", artifact_store=second_store
        )
        self.assertIs(second.status, BusinessAgentStatus.COMPLETED)
        self.assertFalse(second_store.contains("opportunity:run-1"))

    def test_non_callable_handler_is_rejected_during_assembly(self):
        with self.assertRaises(ValueError):
            CapabilityExecutor({"insight": None})


if __name__ == "__main__":
    unittest.main()
