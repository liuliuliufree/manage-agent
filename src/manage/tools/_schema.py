"""Shared JSON Schema fragments for model-visible business tools."""

DATA_SOURCE_PROPERTY = {
    "data_source_id": {
        "type": "string",
        "minLength": 1,
        "description": "要读取的版本化业务数据源标识。",
    }
}


def object_schema(
    properties: dict[str, object],
    required: list[str],
) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
