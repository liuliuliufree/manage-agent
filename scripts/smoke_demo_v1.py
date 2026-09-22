"""Offline end-to-end smoke for the two confirmed Demo V1 request shapes.

All customers, opportunities, strategies, rule results, and execution tasks in
this script are synthetic.  The smoke validates orchestration and artifact
flow; it does not validate real business algorithms or rules.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from openai.types.chat import ChatCompletion

from src.application import (
    ArtifactStore,
    BusinessAgent,
    BusinessAgentStatus,
    CapabilityExecutor,
    CapabilityIO,
    GoalParser,
    Planner,
    RuntimeContext,
)
from src.domain import CapabilityOutput, CapabilityResult, CapabilityStatus
from src.model import FakeChatModel


RUNTIME = RuntimeContext(
    actor_id="synthetic-current-agent",
    channel_id="individual",
    context_source="demo_runtime",
)


class FlowLogger:
    """Print ordered JSONL events without exposing secrets or hidden reasoning."""

    def __init__(self, case_name: str) -> None:
        self._case_name = case_name
        self._sequence = 0

    def emit(self, event: str, **details: object) -> None:
        self._sequence += 1
        
        data = {
            "sequence": self._sequence,
            "case": self._case_name,
            "event": event,
            **details,
        }

        print("{\n" + ",\n".join(
            f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False, default=str)}"
            for k, v in data.items()
        ) + "\n}")
        # print(
        #     json.dumps(
        #         {
        #             "sequence": self._sequence,
        #             "case": self._case_name,
        #             "event": event,
        #             **details,
        #         },
        #         ensure_ascii=False,
        #         default=str,
                
        #     )
        # )


class LoggingFakeChatModel(FakeChatModel):
    def __init__(
        self,
        *,
        component: str,
        logger: FlowLogger,
        response_payload: object,
    ) -> None:
        super().__init__(completions=[_completion(response_payload)])
        self._component = component
        self._logger = logger

    async def complete(self, request):
        messages = request.get("messages", [])
        user_content = next(
            (
                message.get("content")
                for message in messages
                if message.get("role") == "user"
            ),
            None,
        )
        try:
            user_input: Any = json.loads(user_content) if user_content else None
        except (TypeError, json.JSONDecodeError):
            user_input = user_content
        self._logger.emit(
            f"{self._component}.model_request",
            model=request.get("model"),
            response_format=request.get("response_format"),
            temperature=request.get("temperature"),
            user_input=user_input,
        )
        completion = await super().complete(request)
        content = completion.choices[0].message.content
        try:
            model_output: Any = json.loads(content) if content else None
        except json.JSONDecodeError:
            model_output = content
        self._logger.emit(
            f"{self._component}.model_response",
            model_output=model_output,
        )
        return completion


class LoggingGoalParser(GoalParser):
    def __init__(self, *, logger: FlowLogger, **kwargs) -> None:
        super().__init__(**kwargs)
        self._logger = logger

    async def parse(self, **kwargs):
        self._logger.emit(
            "goal_parser.started",
            user_request=kwargs.get("user_request"),
            runtime_context=asdict(kwargs["runtime_context"]),
            has_existing_goal=kwargs.get("existing_goal") is not None,
        )
        result = await super().parse(**kwargs)
        self._logger.emit(
            "goal_parser.completed",
            status=result.status.value,
            error=result.error,
            goal=asdict(result.goal) if result.goal is not None else None,
            missing_information=[asdict(item) for item in result.missing_information],
            diagnostics=result.diagnostics,
        )
        return result


class LoggingPlanner(Planner):
    def __init__(self, *, logger: FlowLogger, **kwargs) -> None:
        super().__init__(**kwargs)
        self._logger = logger

    async def plan(self, **kwargs):
        self._logger.emit(
            "planner.started",
            goal_ref={
                "goal_id": kwargs["goal"].goal_id,
                "version": kwargs["goal"].version,
            },
            context=kwargs.get("context") or {},
            available_capability_ids=list(kwargs["capability_catalog"]),
        )
        result = await super().plan(**kwargs)
        self._logger.emit(
            "planner.completed",
            plan=asdict(result),
        )
        return result


def _completion(payload: object) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-demo-v1-smoke",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                }
            ],
            "created": 0,
            "model": "fake",
            "object": "chat.completion",
        }
    )


@dataclass(frozen=True)
class SmokeCase:
    name: str
    request: str
    parser_payload: dict[str, object]
    planner_payload: dict[str, object]
    initial_customer: dict[str, object] | None = None


CASES = (
    SmokeCase(
        name="full_goal_to_simulated_task",
        request=(
            "当前处于开门红阶段，希望完成500W NBEV，主推御享分红26和"
            "御享金越年金。渠道默认为个险，操作人默认为代理人自己。"
        ),
        parser_payload={
            "goal_type": "performance_achievement",
            "metric_text": "NBEV",
            "target_text": "500W",
            "time_text": "开门红",
            "products": ["御享分红26", "御享金越年金"],
            "needs": [],
            "audience_text": None,
            "constraints": [],
        },
        planner_payload={
            "steps": [
                {
                    "step_id": "inspect",
                    "capability_id": "directional_insight",
                    "depends_on": [],
                },
                {
                    "step_id": "target",
                    "capability_id": "customer_targeting",
                    "depends_on": ["inspect"],
                },
                {
                    "step_id": "strategy",
                    "capability_id": "strategy_generation",
                    "depends_on": ["target"],
                },
                {
                    "step_id": "validate",
                    "capability_id": "validation_distribution",
                    "depends_on": ["target", "strategy"],
                },
            ]
        },
    ),
    SmokeCase(
        name="known_customer_to_simulated_task",
        request="王女士下一步应该怎么经营？",
        parser_payload={
            "goal_type": "opportunity_discovery",
            "metric_text": None,
            "target_text": None,
            "time_text": None,
            "products": [],
            "needs": [],
            "audience_text": "王女士",
            "constraints": [],
        },
        planner_payload={
            "steps": [
                {
                    "step_id": "strategy",
                    "capability_id": "strategy_generation",
                    "depends_on": [],
                },
                {
                    "step_id": "validate",
                    "capability_id": "validation_distribution",
                    "depends_on": ["strategy"],
                },
            ]
        },
        initial_customer={
            "customers": [
                {
                    "customer_id": "synthetic-wang",
                    "display_name": "王女士（虚构）",
                    "channel_id": "individual",
                    "owner_actor_id": "synthetic-current-agent",
                }
            ],
            "data_source": "synthetic_smoke_fixture",
        },
    ),
)


IO = {
    "directional_insight": CapabilityIO(output_types=("opportunity",)),
    "customer_targeting": CapabilityIO(
        required_inputs=("opportunity",),
        output_types=("customer_set",),
    ),
    "strategy_generation": CapabilityIO(
        required_inputs=("customer_set",),
        output_types=("strategy",),
    ),
    "validation_distribution": CapabilityIO(
        required_inputs=("customer_set", "strategy"),
        output_types=("execution_task",),
    ),
}


CATALOG = {
    "directional_insight": {"description": "合成机会发现"},
    "customer_targeting": {"description": "合成圈客"},
    "strategy_generation": {"description": "合成策略"},
    "validation_distribution": {"description": "合成规则校验与模拟分发"},
}


async def run_case(case: SmokeCase) -> None:
    logger = FlowLogger(case.name)
    logger.emit(
        "run.started",
        user_request=case.request,
        runtime_context=asdict(RUNTIME),
        data_mode="synthetic",
    )
    store = ArtifactStore()
    existing_context = None
    if case.initial_customer is not None:
        initial_ref = store.put(
            "customer_set", "known-customer", case.initial_customer
        )
        existing_context = {"customer_set_refs": ["known-customer"]}
        logger.emit(
            "artifact.initialized",
            ref=initial_ref,
            value=case.initial_customer,
            trusted_application_context=existing_context,
        )
    else:
        logger.emit("artifact.initialized", refs=[], trusted_application_context={})

    def directional_insight(request):
        logger.emit(
            "capability.started",
            capability_id=request.capability_id,
            request=asdict(request),
        )
        opportunity = {
            "opportunity_type": "synthetic_demo_opportunity",
            "products": ["御享分红26", "御享金越年金"],
            "source": "synthetic_smoke_fixture",
        }
        ref = store.put(
            "opportunity",
            "synthetic-opportunity",
            opportunity,
        )
        logger.emit("artifact.stored", ref=ref, value=opportunity)
        result = CapabilityResult(
            request.request_id,
            request.capability_id,
            CapabilityStatus.SUCCESS,
            outputs=(
                CapabilityOutput(
                    "synthetic-opportunity", "opportunity", "虚构经营机会"
                ),
            ),
        )
        logger.emit("capability.completed", result=asdict(result))
        return result

    def customer_targeting(request):
        logger.emit(
            "capability.started",
            capability_id=request.capability_id,
            request=asdict(request),
        )
        opportunity = store.get(request.input_refs[0]).value
        logger.emit(
            "artifact.read",
            consumer=request.capability_id,
            ref=request.input_refs[0],
            value=opportunity,
        )
        customer_set = {
            "customers": [
                {
                    "customer_id": "synthetic-customer-a",
                    "display_name": "客户A（虚构）",
                    "channel_id": "individual",
                    "owner_actor_id": "synthetic-current-agent",
                }
            ],
            "derived_from": opportunity["opportunity_type"],
            "data_source": "synthetic_smoke_fixture",
        }
        ref = store.put(
            "customer_set",
            "synthetic-customers",
            customer_set,
        )
        logger.emit("artifact.stored", ref=ref, value=customer_set)
        result = CapabilityResult(
            request.request_id,
            request.capability_id,
            CapabilityStatus.SUCCESS,
            outputs=(
                CapabilityOutput(
                    "synthetic-customers", "customer_set", "虚构候选客户集合"
                ),
            ),
        )
        logger.emit("capability.completed", result=asdict(result))
        return result

    def strategy_generation(request):
        logger.emit(
            "capability.started",
            capability_id=request.capability_id,
            request=asdict(request),
        )
        customer_set = store.get(request.input_refs[0]).value
        logger.emit(
            "artifact.read",
            consumer=request.capability_id,
            ref=request.input_refs[0],
            value=customer_set,
        )
        customers = customer_set["customers"]
        strategy_id = f"synthetic-strategy-{case.name}"
        strategy = {
            "customer_ids": [item["customer_id"] for item in customers],
            "recommendation": "synthetic strategy for artifact-flow verification",
            "source": "synthetic_smoke_handler",
        }
        ref = store.put(
            "strategy",
            strategy_id,
            strategy,
        )
        logger.emit("artifact.stored", ref=ref, value=strategy)
        result = CapabilityResult(
            request.request_id,
            request.capability_id,
            CapabilityStatus.SUCCESS,
            outputs=(CapabilityOutput(strategy_id, "strategy", "虚构经营策略"),),
        )
        logger.emit("capability.completed", result=asdict(result))
        return result

    def validation_distribution(request):
        logger.emit(
            "capability.started",
            capability_id=request.capability_id,
            request=asdict(request),
        )
        artifacts = {
            ref.split(":", 1)[0]: store.get(ref).value
            for ref in request.input_refs
        }
        for ref in request.input_refs:
            logger.emit(
                "artifact.read",
                consumer=request.capability_id,
                ref=ref,
                value=store.get(ref).value,
            )
        customers = artifacts["customer_set"]["customers"]
        allowed = all(
            item["channel_id"] == request.actor_context.channel_id
            and item["owner_actor_id"] == request.actor_context.actor_id
            for item in customers
        )
        logger.emit(
            "rule.evaluated",
            rule_id="synthetic-channel-owner-rule",
            rule_version="synthetic-rule-v1",
            expected_channel_id=request.actor_context.channel_id,
            expected_actor_id=request.actor_context.actor_id,
            customer_assignments=[
                {
                    "customer_id": item["customer_id"],
                    "channel_id": item["channel_id"],
                    "owner_actor_id": item["owner_actor_id"],
                }
                for item in customers
            ],
            allowed=allowed,
        )
        if not allowed:
            result = CapabilityResult(
                request.request_id,
                request.capability_id,
                CapabilityStatus.BLOCKED,
                rule_result_refs=("rule_result:synthetic-channel-owner-block",),
            )
            logger.emit("capability.completed", result=asdict(result))
            return result
        task_id = f"synthetic-task-{case.name}"
        task = {
            "execution_mode": "simulated",
            "channel_id": request.actor_context.channel_id,
            "actor_id": request.actor_context.actor_id,
            "customer_ids": [item["customer_id"] for item in customers],
            "strategy": artifacts["strategy"],
            "rule_version": "synthetic-rule-v1",
            "result": "simulated_task_created",
        }
        ref = store.put(
            "execution_task",
            task_id,
            task,
        )
        logger.emit("artifact.stored", ref=ref, value=task)
        result = CapabilityResult(
            request.request_id,
            request.capability_id,
            CapabilityStatus.SUCCESS,
            outputs=(CapabilityOutput(task_id, "execution_task", "模拟经营任务"),),
            rule_result_refs=("rule_result:synthetic-channel-owner-pass",),
        )
        logger.emit("capability.completed", result=asdict(result))
        return result

    parser_model = LoggingFakeChatModel(
        component="goal_parser",
        logger=logger,
        response_payload=case.parser_payload,
    )
    planner_model = LoggingFakeChatModel(
        component="planner",
        logger=logger,
        response_payload=case.planner_payload,
    )
    agent = BusinessAgent(
        goal_parser=LoggingGoalParser(
            logger=logger,
            model=parser_model,
            model_name="fake",
            goal_id_factory=lambda: f"goal-{case.name}",
        ),
        planner=LoggingPlanner(
            logger=logger,
            model=planner_model,
            model_name="fake",
            plan_id_factory=lambda: f"plan-{case.name}",
        ),
        capability_executor=CapabilityExecutor(
            {
                "directional_insight": directional_insight,
                "customer_targeting": customer_targeting,
                "strategy_generation": strategy_generation,
                "validation_distribution": validation_distribution,
            }
        ),
        capability_io=IO,
        capability_catalog=CATALOG,
    )
    response = await agent.handle(
        user_request=case.request,
        runtime_context=RUNTIME,
        existing_context=existing_context,
        artifact_store=store,
    )

    if response.status is not BusinessAgentStatus.COMPLETED:
        raise AssertionError(f"{case.name} failed: {response}")
    if response.plan is None or response.plan.version != 1:
        raise AssertionError(f"{case.name} did not keep one Plan V1")
    if len(parser_model.requests) != 1 or len(planner_model.requests) != 1:
        raise AssertionError(f"{case.name} exceeded model call expectations")
    task_ref = next(
        ref
        for ref in response.execution_context.published_artifacts
        if ref.startswith("execution_task:")
    )
    task = store.get(task_ref).value
    if task["execution_mode"] != "simulated":
        raise AssertionError(f"{case.name} execution was not marked simulated")
    if task["channel_id"] != "individual":
        raise AssertionError(f"{case.name} bypassed the individual-channel gate")
    logger.emit(
        "run.completed",
        status=response.status.value,
        goal=asdict(response.goal),
        plan=asdict(response.plan),
        step_results={
            step_id: asdict(result)
            for step_id, result in response.execution_context.step_results.items()
        },
        published_artifacts={
            ref: asdict(published)
            for ref, published in response.execution_context.published_artifacts.items()
        },
        final_task_ref=task_ref,
        final_task=task,
    )


async def main() -> None:
    for case in CASES:
        await run_case(case)


if __name__ == "__main__":
    asyncio.run(main())
