from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from llm_core._exceptions import ProviderError
from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)

if TYPE_CHECKING:
    from openai.types.chat import (
        ChatCompletionMessageParam,
        ChatCompletionToolUnionParam,
    )
    from openai.types.chat.completion_create_params import ResponseFormat
    from pydantic import BaseModel

    from llm_core._config import LLMConfig


class OpenAiCompatibleProvider:
    """Generic client for any OpenAI-chat-completions-compatible API.

    Berget.ai is the first configured host (see `create_provider`'s "berget"
    case), but this class takes no Berget-specific behavior — a future second
    OpenAI-compatible host is a new `LLM_PROVIDER`/`LLM_BASE_URL` value, not a
    new provider class.
    """

    def __init__(self, config: LLMConfig, *, default_base_url: str) -> None:
        from openai import AsyncOpenAI

        if not config.berget_api_key:
            raise ValueError("berget_api_key is required for OpenAiCompatibleProvider")

        self._client = AsyncOpenAI(
            api_key=config.berget_api_key,
            base_url=config.base_url or default_base_url,
        )
        self._model = config.model
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens

    def _to_openai_message(self, msg: Message) -> dict[str, Any]:
        match msg.role:
            case Role.system:
                return {"role": "system", "content": msg.content}
            case Role.user:
                return {"role": "user", "content": msg.content}
            case Role.assistant:
                message: dict[str, Any] = {"role": "assistant", "content": msg.content}
                if msg.tool_calls:
                    message["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                return message
            case Role.tool_result:
                return {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content,
                }
            case Role.tool_call:
                # tool_call is never a standalone message role here, mirroring
                # GeminiProvider's handling.
                raise ValueError(f"Cannot map role {msg.role!r} to OpenAI message")

    def _to_openai_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _to_response_format(self, schema: type[BaseModel]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            },
        }

    def _from_openai_message(self, message: Any, raw: Any) -> LLMResponse:
        tool_calls: list[ToolCall] = []
        for tc in message.tool_calls or []:
            call_id = tc.id or str(uuid.uuid4())
            arguments = (
                json.loads(tc.function.arguments) if tc.function.arguments else {}
            )
            tool_calls.append(
                ToolCall(id=call_id, name=tc.function.name, arguments=arguments)
            )

        msg = Message(
            role=Role.assistant,
            content=message.content or "",
            tool_calls=tuple(tool_calls),
        )
        return LLMResponse(message=msg, raw=raw)

    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        from openai import omit

        openai_messages = cast(
            "list[ChatCompletionMessageParam]",
            [self._to_openai_message(m) for m in messages],
        )
        openai_tools = (
            cast("list[ChatCompletionToolUnionParam]", self._to_openai_tools(tools))
            if tools
            else omit
        )
        response_format = (
            cast("ResponseFormat", self._to_response_format(response_schema))
            if response_schema is not None
            else omit
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens if self._max_tokens is not None else omit,
                tools=openai_tools,
                response_format=response_format,
            )
        except Exception as exc:
            raise ProviderError(str(exc), exc) from exc

        return self._from_openai_message(response.choices[0].message, response)

    async def generate_stream(
        self,
        messages: list[Message],
    ) -> AsyncIterator[StreamChunk]:
        from openai import omit

        openai_messages = cast(
            "list[ChatCompletionMessageParam]",
            [self._to_openai_message(m) for m in messages],
        )

        try:
            sdk_stream = await self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                stream=True,
                temperature=self._temperature,
                max_tokens=self._max_tokens if self._max_tokens is not None else omit,
            )
        except Exception as exc:
            raise ProviderError(str(exc), exc) from exc

        return self._iter_stream(sdk_stream)

    async def _iter_stream(self, sdk_stream: Any) -> AsyncGenerator[StreamChunk, None]:
        try:
            async for chunk in sdk_stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield StreamChunk(text=delta.content, raw=chunk)
        except Exception as exc:
            raise ProviderError(str(exc), exc) from exc
