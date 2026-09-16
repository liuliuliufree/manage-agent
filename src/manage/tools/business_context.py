"""Tool for reading the goal, boundaries, metadata, and applicable rules."""

from typing import Any, Mapping

from agent import Tool

from ._context import ToolContext
from ._schema import DATA_SOURCE_PROPERTY, object_schema


def create_tool(context: ToolContext) -> Tool:
    name = "get_business_context"

    def handle(arguments: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(arguments)
        result = context.service(values["data_source_id"]).get_business_context().to_dict()
        return context.observe(name, values, result)

    return Tool(
        name=name,
        title="理解目标与边界",
        description=(
            "读取一个业务数据源中的经营目标、数据范围、授权边界、系统硬规则和版本信息。"
            "当任务需要理解业务背景、规则或数据口径时使用；它不产生机会推荐。"
        ),
        parameters=object_schema(dict(DATA_SOURCE_PROPERTY), ["data_source_id"]),
        handler=handle,
    )
