"""Model-visible Tool adapters for deterministic management capabilities."""

from __future__ import annotations

from typing import Any

from agent import Tool

from .errors import ManageError
from .repository import ScenarioRepository
from .service import ManageService


class ManageToolSession:
    """Keep formal artifacts produced during one observable Agent run."""

    def __init__(self, repository: ScenarioRepository) -> None:
        self._repository = repository
        self._services: dict[str, ManageService] = {}
        self.business_contexts: dict[str, dict[str, Any]] = {}
        self.opportunity_analyses: dict[str, dict[str, Any]] = {}
        self.segment_results: dict[tuple[str, str], dict[str, Any]] = {}
        self.customer_decisions: dict[tuple[str, str, str], dict[str, Any]] = {}

    def tools(self) -> list[Tool]:
        scenario_parameter = {
            "scenario_id": {
                "type": "string",
                "minLength": 1,
                "description": "场景标识，例如 demo-acts-1-3。",
            }
        }
        return [
            Tool(
                name="get_business_context",
                description=(
                    "读取指定场景的经营请求、场景元数据、数据范围、用户明确边界和当前适用的版本化规则。"
                    "开始新的前三幕分析时首先使用。本工具只返回输入事实和规则上下文，不返回机会推荐、圈客名单或测试期望。"
                ),
                parameters={
                    "type": "object",
                    "properties": scenario_parameter,
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=self._get_business_context,
            ),
            Tool(
                name="analyze_opportunities",
                description=(
                    "基于指定场景的数据快照和规则版本，确定性识别全部候选机会，计算可比较指标并返回稳定排序、"
                    "推荐项、证据、风险、置信度和限制。在推荐任何经营机会前必须使用，不要根据机会名称自行推断排名。"
                ),
                parameters={
                    "type": "object",
                    "properties": scenario_parameter,
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=self._analyze_opportunities,
            ),
            Tool(
                name="segment_opportunity_customers",
                description=(
                    "对指定场景中的一个已识别机会执行确定性客户分层：识别机会客户，应用授权、拒绝、敏感状态、"
                    "频控和初步适当性等硬规则，再对可经营客户评分排序。返回由客户明细派生的漏斗、排除分布和优先客户摘要。"
                    "高分不能覆盖硬规则失败。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        **scenario_parameter,
                        "opportunity_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "机会分析结果中的机会标识。",
                        },
                    },
                    "required": ["scenario_id", "opportunity_id"],
                    "additionalProperties": False,
                },
                handler=self._segment_opportunity_customers,
            ),
            Tool(
                name="explain_customer_decision",
                description=(
                    "返回指定客户在指定机会下的决策证据，包括相关事实及时间、全部硬规则结果、主要处置原因、"
                    "评分贡献、规则与数据版本，以及当前允许和禁止的动作。仅用于解释具体客户，不用于批量搜索客户。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        **scenario_parameter,
                        "opportunity_id": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "customer_id": {
                            "type": "string",
                            "pattern": "^C[0-9]{3}$",
                        },
                    },
                    "required": ["scenario_id", "opportunity_id", "customer_id"],
                    "additionalProperties": False,
                },
                handler=self._explain_customer_decision,
            ),
        ]

    def service(self, scenario_id: str) -> ManageService:
        service = self._services.get(scenario_id)
        if service is None:
            service = ManageService(self._repository.load(scenario_id))
            self._services[scenario_id] = service
        return service

    def _get_business_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        scenario_id = arguments["scenario_id"]
        result = self.service(scenario_id).get_business_context().to_dict()
        self.business_contexts[scenario_id] = result
        return result

    def _analyze_opportunities(self, arguments: dict[str, Any]) -> dict[str, Any]:
        scenario_id = arguments["scenario_id"]
        if scenario_id not in self.business_contexts:
            raise ManageError("get_business_context must be called first")
        result = self.service(scenario_id).analyze_opportunities().to_dict()
        self.opportunity_analyses[scenario_id] = result
        return result

    def _segment_opportunity_customers(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        scenario_id = arguments["scenario_id"]
        opportunity_id = arguments["opportunity_id"]
        analysis = self.opportunity_analyses.get(scenario_id)
        if analysis is None:
            raise ManageError("analyze_opportunities must be called first")
        known_ids = {
            item["opportunity_id"] for item in analysis["opportunities"]
        }
        if opportunity_id not in known_ids:
            raise ManageError("Opportunity is not present in the current analysis")
        result = (
            self.service(scenario_id)
            .segment_opportunity_customers(opportunity_id)
            .to_dict()
        )
        self.segment_results[(scenario_id, opportunity_id)] = result
        return result

    def _explain_customer_decision(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        scenario_id = arguments["scenario_id"]
        opportunity_id = arguments["opportunity_id"]
        customer_id = arguments["customer_id"]
        if (scenario_id, opportunity_id) not in self.segment_results:
            raise ManageError("segment_opportunity_customers must be called first")
        result = (
            self.service(scenario_id)
            .explain_customer_decision(opportunity_id, customer_id)
            .to_dict()
        )
        self.customer_decisions[(scenario_id, opportunity_id, customer_id)] = result
        return result
