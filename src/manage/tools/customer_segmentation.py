"""Tool for deterministic customer eligibility and prioritisation."""

from typing import Any, Mapping

from agent import Tool

from ._context import ToolContext
from ._schema import DATA_SOURCE_PROPERTY, object_schema


def create_tool(context: ToolContext) -> Tool:
    name = "segment_opportunity_customers"
    properties = {
        **DATA_SOURCE_PROPERTY,
        "opportunity_id": {
            "type": "string",
            "minLength": 1,
            "description": "要执行客户分层的机会标识。",
        },
    }

    def handle(arguments: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(arguments)
        result = context.service(values["data_source_id"]).segment_opportunity_customers(
            values["opportunity_id"]
        ).to_dict()
        return context.observe(name, values, result)

    return Tool(
        name=name,
        title="筛选目标客户",
        description=(
            "对指定机会执行客户识别、硬规则筛选和优先级排序，返回漏斗、排除原因和客户摘要。"
            "本工具可独立调用；高分不会覆盖授权、拒绝、敏感状态、频控或适当性规则。"
        ),
        parameters=object_schema(
            properties,
            ["data_source_id", "opportunity_id"],
        ),
        handler=handle,
    )
