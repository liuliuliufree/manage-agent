"""Small tool boundary used by the agent loop."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from jsonschema import FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for


ToolHandler = Callable[[Mapping[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Tool:
    """A model-visible function and the application code that implements it."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: ToolHandler
    _validator: Validator = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        schema = dict(self.parameters)
        validator_class = validator_for(schema)
        try:
            validator_class.check_schema(schema)
        except SchemaError as exc:
            raise ValueError(
                f"Invalid JSON Schema for tool {self.name!r}: {exc.message}"
            ) from exc
        object.__setattr__(
            self,
            "_validator",
            validator_class(schema, format_checker=FormatChecker()),
        )

    def as_chat_completion_tool(self) -> dict[str, Any]:
        """Return the OpenAI Chat Completions function-tool shape."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }

    def validate_arguments(self, arguments: Mapping[str, Any]) -> None:
        """Validate parsed arguments against the model-visible JSON Schema."""
        errors = sorted(
            self._validator.iter_errors(arguments),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.message,
            ),
        )
        if not errors:
            return

        details = [
            f"{_json_path(error.absolute_path)}: {error.message}"
            for error in errors[:5]
        ]
        if len(errors) > 5:
            details.append(f"and {len(errors) - 5} more error(s)")
        raise ValueError("; ".join(details))


def _json_path(parts: Any) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path
