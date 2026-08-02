from __future__ import annotations


class LLMError(Exception):
    pass


class ProviderError(LLMError):
    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class MissingCredentialError(LLMError):
    """A provider was constructed without the API key or base URL it needs."""


class LLMDisabledError(LLMError):
    """Something called a provider that was deliberately configured as absent.

    Distinct from `MissingCredentialError`: that one means "you meant to
    configure a host and did not", this one means "you meant not to". Raised
    only by `NullProvider`, and only on use — constructing it always succeeds.
    """


class ToolExecutionError(LLMError):
    def __init__(
        self, tool_name: str, message: str, cause: Exception | None = None
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.__cause__ = cause


class MaxIterationsError(LLMError):
    pass
