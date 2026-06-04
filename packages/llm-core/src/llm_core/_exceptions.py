from __future__ import annotations


class LLMError(Exception):
    pass


class ProviderError(LLMError):
    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class ToolExecutionError(LLMError):
    def __init__(
        self, tool_name: str, message: str, cause: Exception | None = None
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.__cause__ = cause


class MaxIterationsError(LLMError):
    pass
