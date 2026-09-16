"""Tool for explaining one customer's deterministic decision evidence."""

from typing import Any, Mapping

from agent import Tool

from ._context import ToolContext
from ._schema import DATA_SOURCE_PROPERTY, object_schema


def create_tool(context: ToolContext) -> Tool:
    name = "explain_customer_decision"
    properties = {
        **DATA_SOURCE_PROPERTY,
        "opportunity_id": {"type": "string", "minLength": 1},
        "customer_id": {"type": "string", "minLength": 1},
    }

    def handle(arguments: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(arguments)
        result = context.service(values["data_source_id"]).explain_customer_decision(
            values["opportunity_id"], values["customer_id"]
        ).to_dict()
        return context.observe(name, values, result)

    return Tool(
        name=name,
        title="核对客户决策证据",
        description=(
            "解释指定客户在某个机会下的事实证据、全部硬规则结果、评分贡献以及允许和禁止动作。"
            "当用户要求核对具体客户或需要个体证据时使用，不用于重建全量客户数据。"
        ),
        parameters=object_schema(
            properties,
            ["data_source_id", "opportunity_id", "customer_id"],
        ),
        handler=handle,
    )
