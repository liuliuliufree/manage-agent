import unittest

from src.application.capability.artifact_flow import (
    ArtifactFlowError,
    CapabilityIO,
    normalize_initial_refs,
    resolve_input_refs,
)
from src.application.capability.artifact_store import ArtifactStore
from src.application.capability.capability_executor import CapabilityExecutor
from src.application.capability.continuation import is_plan_finished
from src.application.capability.execution_context import ExecutionContext
from src.application.capability.step_execution import execute_step
from src.application.capability.step_resolution import is_step_ready
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


def make_goal(goal_id="goal-1"):
    return Goal(
        goal_id=goal_id,
        version=1,
        original_request="虚构测试目标",
        goal_type="opportunity_discovery",
        channel_and_actor=ChannelAndActor("individual", "agent-1", "demo_runtime"),
    )


def make_plan(*steps):
    return Plan(
        plan_id="plan-1",
        version=1,
        goal_ref=GoalRef("goal-1", 1),
        status=PlanStatus.ACTIVE,
        steps=tuple(steps),
    )


def success(request, *outputs):
    return CapabilityResult(
        request_id=request.request_id,
        capability_id=request.capability_id,
        status=CapabilityStatus.SUCCESS,
        outputs=tuple(outputs),
        evidence_refs=("evidence:synthetic",),
    )


class ArtifactStoreTests(unittest.TestCase):
    def test_put_get_deep_copy_and_reference_validation(self):
        store = ArtifactStore()
        original = {"customers": [{"id": "fictional-a"}]}
        ref = store.put("customer_set", "set-1", original)
        original["customers"][0]["id"] = "changed-outside"
        read = store.get(ref)
        self.assertEqual(read.value["customers"][0]["id"], "fictional-a")
        read.value["customers"][0]["id"] = "changed-read"
        self.assertEqual(store.get(ref).value["customers"][0]["id"], "fictional-a")
        for invalid in ["missing-colon", "too:many:colons", ":id", "type:"]:
            with self.subTest(invalid=invalid), self.assertRaises(ArtifactFlowError):
                store.get(invalid)

    def test_duplicate_ref_rejected_but_same_id_other_type_is_allowed(self):
        store = ArtifactStore()
        store.put("opportunity", "same", {"value": 1})
        with self.assertRaises(ArtifactFlowError) as caught:
            store.put("opportunity", "same", {"value": 2})
        self.assertEqual(caught.exception.code, "ARTIFACT_DUPLICATE")
        self.assertEqual(store.put("customer_set", "same", {"value": 3}), "customer_set:same")

    def test_store_binding_prevents_reuse_and_goal_change(self):
        store = ArtifactStore()
        store.bind_goal(GoalRef("goal-1", 1))
        with self.assertRaises(ArtifactFlowError) as reused:
            store.bind_goal(GoalRef("goal-1", 1))
        self.assertEqual(reused.exception.code, "ARTIFACT_STORE_REUSED")
        store2 = ArtifactStore()
        store2.bind_goal(GoalRef("goal-1", 1))
        with self.assertRaises(ArtifactFlowError) as changed:
            store2.bind_goal(GoalRef("goal-2", 1))
        self.assertEqual(changed.exception.code, "ARTIFACT_GOAL_CHANGED")


class ArtifactFlowUnitTests(unittest.TestCase):
    def test_capability_io_contract_validation(self):
        CapabilityIO(required_inputs=("opportunity",), output_types=("customer_set",))
        for kwargs in [
            {"required_inputs": ("opportunity", "opportunity")},
            {"required_inputs": ("opportunity",), "optional_inputs": ("opportunity",)},
            {"output_types": ("bad:type",)},
            {"required_inputs": ("rule_result",)},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CapabilityIO(**kwargs)

    def test_initial_refs_are_validated_deduplicated_and_not_identity_refs(self):
        store = ArtifactStore()
        store.put("opportunity", "opp-1", {"segment": "fictional-a"})
        refs = normalize_initial_refs(
            {"opportunity_refs": ["opp-1", "opp-1"]},
            store=store,
            allowed_types=frozenset({"opportunity"}),
        )
        self.assertEqual(refs, ("opportunity:opp-1",))
        invalid = [
            {"actor_refs": ["agent-1"]},
            {"opportunity_refs": "opp-1"},
            {"opportunity_refs": ["missing"]},
            {"payload": [{}]},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ArtifactFlowError):
                normalize_initial_refs(
                    value,
                    store=store,
                    allowed_types=frozenset({"opportunity"}),
                )

    def test_missing_and_ambiguous_required_or_optional_input_stop(self):
        step = PlanStep("target", "targeting")
        context = ExecutionContext(make_goal(), make_plan(step))
        with self.assertRaises(ArtifactFlowError) as missing:
            resolve_input_refs(step, context, CapabilityIO(required_inputs=("opportunity",)))
        self.assertEqual(missing.exception.code, "INPUT_REQUIRED")
        self.assertEqual(missing.exception.missing_information[0].field, "input_refs.opportunity")

        for artifact_id in ("one", "two"):
            context.artifact_store.put("opportunity", artifact_id, {"id": artifact_id})
        context.initial_refs = ("opportunity:one", "opportunity:two")
        for io in [
            CapabilityIO(required_inputs=("opportunity",)),
            CapabilityIO(optional_inputs=("opportunity",)),
        ]:
            with self.subTest(io=io), self.assertRaises(ArtifactFlowError) as ambiguous:
                resolve_input_refs(step, context, io)
            self.assertEqual(ambiguous.exception.code, "INPUT_AMBIGUOUS")

    def test_direct_dependency_wins_and_ancestor_or_unrelated_output_is_not_used(self):
        root = PlanStep("root", "produce")
        middle = PlanStep("middle", "noop", ("root",))
        consumer = PlanStep("consumer", "consume", ("middle",))
        plan = make_plan(root, middle, consumer)
        store = ArtifactStore()
        store.put("opportunity", "initial", {"kind": "initial"})
        store.put("opportunity", "direct", {"kind": "direct"})
        context = ExecutionContext(
            make_goal(),
            plan,
            artifact_store=store,
            initial_refs=("opportunity:initial",),
        )
        root_result = CapabilityResult("r-root", "produce", CapabilityStatus.SUCCESS)
        middle_result = CapabilityResult("r-middle", "noop", CapabilityStatus.SUCCESS)
        context.record_result("root", root_result)
        context.record_result("middle", middle_result)
        from src.application.capability.artifact_flow import PublishedArtifact
        from src.domain import PlanRef

        context.published_artifacts["opportunity:direct"] = PublishedArtifact(
            "opportunity:direct", "middle", "r-middle", PlanRef("plan-1", 1)
        )
        self.assertEqual(
            resolve_input_refs(
                consumer, context, CapabilityIO(required_inputs=("opportunity",))
            ),
            ("opportunity:direct",),
        )
        context.published_artifacts["opportunity:direct"] = PublishedArtifact(
            "opportunity:direct", "root", "r-root", PlanRef("plan-1", 1)
        )
        self.assertEqual(
            resolve_input_refs(
                consumer, context, CapabilityIO(required_inputs=("opportunity",))
            ),
            ("opportunity:initial",),
        )

    def test_no_input_and_missing_optional_input_yield_empty_refs(self):
        step = PlanStep("inspect", "insight")
        context = ExecutionContext(make_goal(), make_plan(step))
        self.assertEqual(resolve_input_refs(step, context, CapabilityIO()), ())
        self.assertEqual(
            resolve_input_refs(
                step, context, CapabilityIO(optional_inputs=("opportunity",))
            ),
            (),
        )

    def test_result_identity_and_type_are_checked_before_recording(self):
        step = PlanStep("inspect", "insight")
        context = ExecutionContext(make_goal(), make_plan(step))

        def wrong(request):
            return CapabilityResult("wrong", request.capability_id, CapabilityStatus.SUCCESS)

        with self.assertRaises(ArtifactFlowError) as caught:
            execute_step(step, context, CapabilityExecutor({"insight": wrong}), io=CapabilityIO())
        self.assertEqual(caught.exception.code, "RESULT_IDENTITY_MISMATCH")
        self.assertEqual(context.step_results, {})

        context2 = ExecutionContext(make_goal(), make_plan(step))
        with self.assertRaises(ArtifactFlowError) as invalid:
            execute_step(
                step,
                context2,
                CapabilityExecutor({"insight": lambda request: {"not": "a result"}}),
                io=CapabilityIO(),
            )
        self.assertEqual(invalid.exception.code, "RESULT_INVALID")

    def test_output_validation_is_atomic_and_does_not_publish_payload(self):
        step = PlanStep("inspect", "insight")
        context = ExecutionContext(make_goal(), make_plan(step))

        def handler(request):
            context.artifact_store.put("opportunity", "valid", {"value": "first"})
            return success(
                request,
                CapabilityOutput("valid", "opportunity", "synthetic", payload={"display": 1}),
                CapabilityOutput("missing", "strategy", "synthetic"),
            )

        with self.assertRaises(ArtifactFlowError):
            execute_step(
                step,
                context,
                CapabilityExecutor({"insight": handler}),
                io=CapabilityIO(output_types=("opportunity", "strategy")),
            )
        self.assertEqual(context.step_results, {})
        self.assertEqual(context.published_artifacts, {})
        self.assertTrue(context.artifact_store.contains("opportunity:valid"))

    def test_duplicate_and_output_cardinality_are_rejected(self):
        for output_ids, expected in [
            (("one", "one"), "OUTPUT_CARDINALITY_INVALID"),
            (("one", "two"), "OUTPUT_CARDINALITY_INVALID"),
        ]:
            step = PlanStep("inspect", "insight")
            context = ExecutionContext(make_goal(), make_plan(step))

            def handler(request, ids=output_ids):
                for artifact_id in set(ids):
                    context.artifact_store.put("opportunity", artifact_id, {"id": artifact_id})
                return success(
                    request,
                    *(CapabilityOutput(item, "opportunity", "synthetic") for item in ids),
                )

            with self.subTest(output_ids=output_ids), self.assertRaises(ArtifactFlowError) as caught:
                execute_step(
                    step,
                    context,
                    CapabilityExecutor({"insight": handler}),
                    io=CapabilityIO(output_types=("opportunity",)),
                )
            self.assertEqual(caught.exception.code, expected)

    def test_non_success_never_publishes_and_partial_does_not_release_dependency(self):
        statuses = [
            CapabilityStatus.PARTIAL_SUCCESS,
            CapabilityStatus.NO_RESULT,
            CapabilityStatus.NEED_INFORMATION,
            CapabilityStatus.BLOCKED,
            CapabilityStatus.FAILED,
        ]
        for status in statuses:
            first = PlanStep("first", "producer")
            second = PlanStep("second", "consumer", ("first",))
            context = ExecutionContext(make_goal(), make_plan(first, second))

            def handler(request, current=status):
                kwargs = {}
                if current is CapabilityStatus.PARTIAL_SUCCESS:
                    kwargs["limitations"] = ("synthetic limitation",)
                elif current is CapabilityStatus.NEED_INFORMATION:
                    kwargs["missing_information"] = (
                        MissingInformation("x", "missing", "blocks", True),
                    )
                elif current is CapabilityStatus.BLOCKED:
                    kwargs["rule_result_refs"] = ("rule_result:synthetic",)
                elif current is CapabilityStatus.FAILED:
                    kwargs["errors"] = (
                        CapabilityError(ErrorCategory.INTERNAL, "synthetic", "failed"),
                    )
                return CapabilityResult(
                    request.request_id,
                    request.capability_id,
                    current,
                    outputs=(CapabilityOutput("ignored", "opportunity", "ignored"),),
                    **kwargs,
                )

            result = execute_step(
                first,
                context,
                CapabilityExecutor({"producer": handler}),
                io=CapabilityIO(output_types=("opportunity",)),
            )
            self.assertIs(result.status, status)
            self.assertEqual(context.published_artifacts, {})
            self.assertFalse(is_step_ready(second, context))
            self.assertFalse(is_plan_finished(context.current_plan, context))

    def test_repeated_or_changed_context_step_is_rejected_before_handler(self):
        calls = []
        step = PlanStep("one", "cap")
        context = ExecutionContext(make_goal(), make_plan(step))

        def handler(request):
            calls.append(request)
            return success(request)

        executor = CapabilityExecutor({"cap": handler})
        execute_step(step, context, executor, io=CapabilityIO())
        with self.assertRaises(ArtifactFlowError) as repeated:
            execute_step(step, context, executor, io=CapabilityIO())
        self.assertEqual(repeated.exception.code, "STEP_NOT_READY")
        self.assertEqual(len(calls), 1)

        context2 = ExecutionContext(make_goal(), make_plan(step))
        context2.goal = make_goal("goal-2")
        with self.assertRaises(ArtifactFlowError) as changed:
            execute_step(step, context2, executor, io=CapabilityIO())
        self.assertEqual(changed.exception.code, "ARTIFACT_GOAL_CHANGED")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
