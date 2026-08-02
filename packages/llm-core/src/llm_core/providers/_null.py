from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from llm_core._exceptions import LLMDisabledError
from llm_core._types import LLMResponse, Message, StreamChunk, ToolDefinition

if TYPE_CHECKING:
    from pydantic import BaseModel

    from llm_core._config import LLMConfig


class NullProvider:
    """A provider that is configured to not exist.

    Constructing it always succeeds — no key, no base URL, no client library —
    so a process whose LLM steps are switched off starts normally instead of
    dying on a credential it will never use. Every call raises
    `LLMDisabledError` instead, at the site that actually wanted a model.

    Selected with `kind: none` in `llm_config.yaml`, or `LLM_PROVIDER=none` to
    disable every role at once.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._model = config.model

    def _refuse(self, operation: str) -> LLMDisabledError:
        return LLMDisabledError(
            f"{operation} was called on a provider configured as 'none' "
            f"(requested model: {self._model!r}). Point the role at a real "
            f"provider in llm_config.yaml, or unset LLM_PROVIDER=none."
        )

    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        raise self._refuse("generate")

    async def generate_stream(
        self,
        messages: list[Message],
    ) -> AsyncIterator[StreamChunk]:
        # A coroutine returning an iterator, not an async generator — same shape
        # as the real providers, so the refusal surfaces on await rather than on
        # the first `async for`.
        raise self._refuse("generate_stream")
