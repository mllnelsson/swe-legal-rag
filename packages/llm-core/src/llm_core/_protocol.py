from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from pydantic import BaseModel

from llm_core._types import LLMResponse, Message, StreamChunk, ToolDefinition


@runtime_checkable
class LLMProvider(Protocol):
    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse: ...

    async def generate_stream(
        self,
        messages: list[Message],
    ) -> AsyncIterator[StreamChunk]: ...
