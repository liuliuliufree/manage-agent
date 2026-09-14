"""Errors exposed by the model access boundary."""


class ModelCallError(RuntimeError):
    """A normalized failure from an LLM request.

    Chat Completions messages and responses remain provider-native. Only
    infrastructure errors are normalized so the agent runtime does not depend
    on one SDK's exception hierarchy.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
