"""Configuration for an OpenAI-compatible Chat Completions endpoint."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from dotenv import dotenv_values


@dataclass(frozen=True, slots=True)
class ChatModelSettings:
    """Validated settings loaded from the environment and an optional .env."""

    base_url: str
    api_key: str = field(repr=False)
    model: str
    timeout_seconds: float = 60.0
    max_retries: int = 2

    @classmethod
    def from_env(
        cls,
        env_file: str | Path | None = ".env",
    ) -> "ChatModelSettings":
        file_values = dotenv_values(env_file) if env_file is not None else {}

        def read(name: str) -> str | None:
            value = os.environ.get(name)
            if value is None:
                value = file_values.get(name)
            return value.strip() if isinstance(value, str) else None

        values = {
            "BASE_URL": read("BASE_URL"),
            "API_KEY": read("API_KEY"),
            "MODEL": read("MODEL"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError(
                f"Missing model configuration: {', '.join(missing)}"
            )

        base_url = cast(str, values["BASE_URL"])
        api_key = cast(str, values["API_KEY"])
        model = cast(str, values["MODEL"])
        return cls(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=model,
        )
