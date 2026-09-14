"""Stable boundary used by the future agent runtime."""

from collections.abc import AsyncIterator
from typing import Protocol

from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.completion_create_params import CompletionCreateParamsBase


class ChatModel(Protocol):
    """A model that speaks the OpenAI Chat Completions protocol."""

    async def complete(
        self,
        request: CompletionCreateParamsBase,
    ) -> ChatCompletion:
        """Create one non-streaming chat completion."""
        ...

    def stream(
        self,
        request: CompletionCreateParamsBase,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Create a streaming chat completion and yield raw SDK chunks."""
        ...

    async def close(self) -> None:
        """Release resources owned by the model implementation."""
        ...
