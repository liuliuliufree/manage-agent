"""Deterministic Chat Completions implementation for agent tests."""

from collections import deque
from collections.abc import AsyncIterator, Iterable
from copy import deepcopy

from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.completion_create_params import CompletionCreateParamsBase


class FakeChatModel:
    """Return preconfigured SDK response objects without network access."""

    def __init__(
        self,
        *,
        completions: Iterable[ChatCompletion] = (),
        chunks: Iterable[ChatCompletionChunk] = (),
        chunk_streams: Iterable[Iterable[ChatCompletionChunk]] | None = None,
    ) -> None:
        self._completions = deque(completions)
        self._chunk_streams = deque(
            [list(stream) for stream in chunk_streams]
            if chunk_streams is not None
            else [list(chunks)]
        )
        self.requests: list[CompletionCreateParamsBase] = []

    async def complete(
        self,
        request: CompletionCreateParamsBase,
    ) -> ChatCompletion:
        self.requests.append(deepcopy(request))
        if not self._completions:
            raise AssertionError("No fake completion configured")
        return self._completions.popleft()

    async def stream(
        self,
        request: CompletionCreateParamsBase,
    ) -> AsyncIterator[ChatCompletionChunk]:
        self.requests.append(deepcopy(request))
        if not self._chunk_streams:
            raise AssertionError("No fake chunk stream configured")
        for chunk in self._chunk_streams.popleft():
            yield chunk

    async def close(self) -> None:
        pass
