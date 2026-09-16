"""Tool for deterministic opportunity discovery and comparison."""

from typing import Any, Mapping

from agent import Tool

from ._context import ToolContext
from ._schema import DATA_SOURCE_PROPERTY, object_schema


def create_tool(context: ToolContext) -> Tool:
    name = "analyze_opportunities"

    def handle(arguments: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(arguments)
        result = context.service(values["data_source_id"]).analyze_opportunities().to_dict()
        return context.observe(name, values, result)

    return Tool(
        name=name,
        title="发现并比较机会",
        description=(
            "从版本化业务事实中确定性识别全部已配置机会，计算比较指标、限制、置信度和稳定排序。"
            "当任务涉及机会发现、比较或推荐时使用；不要仅凭机会名称猜测排名。"
        ),
        parameters=object_schema(dict(DATA_SOURCE_PROPERTY), ["data_source_id"]),
        handler=handle,
    )
