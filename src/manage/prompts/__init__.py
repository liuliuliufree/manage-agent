"""Prompt entry points owned by the management agent package."""

from .management import SYSTEM_PROMPT, build_user_prompt

__all__ = ["SYSTEM_PROMPT", "build_user_prompt"]
