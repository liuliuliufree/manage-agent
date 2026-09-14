"""OpenAI-compatible Chat Completions implementation."""

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.completion_create_params import CompletionCreateParamsBase

from .errors import ModelCallError
from .settings import ChatModelSettings


class OpenAIChatModel:
    """Thin access layer over ``client.chat.completions.create()``."""

    def __init__(
        self,
        settings: ChatModelSettings,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )

    @property
    def default_model(self) -> str:
        return self._settings.model

    async def complete(
        self,
        request: CompletionCreateParamsBase,
    ) -> ChatCompletion:
        """Return the SDK's native non-streaming response."""
        try:
            response = await self._client.chat.completions.create(
                **request,
                stream=False,
            )
            return cast(ChatCompletion, response)
        except APITimeoutError as exc:
            raise ModelCallError(
                "Model request timed out",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise ModelCallError(
                "Unable to connect to model provider",
                retryable=True,
            ) from exc
        except APIStatusError as exc:
            raise self._from_status_error(exc) from exc

    async def stream(
        self,
        request: CompletionCreateParamsBase,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Yield the SDK's native streaming chunks without translating them."""
        try:
            response_context = self._client.chat.completions.with_streaming_response.create(
                **request,
                stream=True,
            )
            async with response_context as response:
                data_lines: list[str] = []
                async for line in response.iter_lines():
                    if line == "":
                        chunk = self._parse_sse_event(data_lines)
                        data_lines.clear()
                        if chunk is not None:
                            yield chunk
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip(" "))

                chunk = self._parse_sse_event(data_lines)
                if chunk is not None:
                    yield chunk
        except APITimeoutError as exc:
            raise ModelCallError(
                "Model stream timed out",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise ModelCallError(
                "Model stream connection failed",
                retryable=True,
            ) from exc
        except APIStatusError as exc:
            raise self._from_status_error(exc) from exc

    async def close(self) -> None:
        await self._client.close()

    @staticmethod
    def _parse_sse_event(data_lines: list[str]) -> ChatCompletionChunk | None:
        if not data_lines:
            return None
        data = "\n".join(data_lines)
        if data == "[DONE]":
            return None
        try:
            payload: Any = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ModelCallError(
                "Model stream returned invalid JSON",
                retryable=False,
            ) from exc
        if isinstance(payload, dict) and "error" in payload:
            error = payload["error"]
            message = error.get("message") if isinstance(error, dict) else None
            detail = message if isinstance(message, str) else "unknown provider error"
            raise ModelCallError(
                f"Model stream returned an error: {detail}",
                retryable=False,
            )
        try:
            return ChatCompletionChunk.model_validate(payload)
        except ValueError as exc:
            raise ModelCallError(
                "Model stream returned an invalid chunk",
                retryable=False,
            ) from exc

    @staticmethod
    def _from_status_error(error: APIStatusError) -> ModelCallError:
        status_code = error.status_code
        retryable = status_code in {408, 409, 429} or status_code >= 500
        return ModelCallError(
            f"Model provider returned HTTP {status_code}",
            retryable=retryable,
            status_code=status_code,
        )
