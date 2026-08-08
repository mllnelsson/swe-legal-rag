from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from llm_core._clients import get_async_openai
from llm_core._exceptions import MissingCredentialError, ProviderError
from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)

if TYPE_CHECKING:
    from openai import AsyncOpenAI
    from openai.types.chat import (
        ChatCompletionMessageParam,
        ChatCompletionToolUnionParam,
    )
    from openai.types.chat.completion_create_params import ResponseFormat
    from pydantic import BaseModel

    from llm_core._config import LLMConfig


def _usage_from_openai(usage: Any) -> Usage | None:
    if usage is None:
        return None
    return Usage(
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


class OpenAiCompatibleProvider:
    """Generic client for any OpenAI-chat-completions-compatible API.

    Takes no host-specific behavior: a second OpenAI-compatible host is a new
    `base_url`, not a new provider class. Both credentials are required rather
    than defaulted — a wrong-but-present default silently sends traffic to the
    wrong host, which is harder to diagnose than a refusal to start.
    """

    def __init__(self, config: LLMConfig) -> None:
        if not config.api_key:
            raise MissingCredentialError(
                "An API key is required for OpenAiCompatibleProvider. Set it via "
                "the provider's api_key_env in llm_config.yaml, or LLM_API_KEY."
            )
        if not config.base_url:
            raise MissingCredentialError(
                "A base URL is required for OpenAiCompatibleProvider. Set it via "
                "the provider's base_url in llm_config.yaml, or LLM_BASE_URL."
            )

        # Credentials are checked here but the client is not built here: it owns
        # a connection pool that cannot outlive the event loop that filled it,
        # and a provider is routinely constructed outside any loop and then used
        # from a different one per message. See `llm_core._clients`.
        self._api_key = config.api_key
        self._base_url = config.base_url
        self._model = config.model
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens
        self._provider_name = config.provider
        self._stream_usage = config.stream_usage

    def _client(self) -> AsyncOpenAI:
        """The client belonging to the loop this call is running on."""
        return get_async_openai(api_key=self._api_key, base_url=self._base_url)

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
        return LLMResponse(
            message=msg,
            raw=raw,
            usage=_usage_from_openai(getattr(raw, "usage", None)),
            model=self._response_model(raw),
            provider=self._provider_name,
        )

    def _response_model(self, raw: Any) -> str:
        """The model the API says it served, not the one we asked for.

        Hosts routinely resolve an alias to a dated build, and cost must be
        attributed to what actually ran.
        """
        return getattr(raw, "model", None) or self._model

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
            response = await self._client().chat.completions.create(
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
            sdk_stream = await self._client().chat.completions.create(
                model=self._model,
                messages=openai_messages,
                stream=True,
                stream_options={"include_usage": True} if self._stream_usage else omit,
                temperature=self._temperature,
                max_tokens=self._max_tokens if self._max_tokens is not None else omit,
            )
        except Exception as exc:
            raise ProviderError(str(exc), exc) from exc

        return self._iter_stream(sdk_stream)

    async def _iter_stream(self, sdk_stream: Any) -> AsyncGenerator[StreamChunk, None]:
        try:
            async for chunk in sdk_stream:
                usage = _usage_from_openai(getattr(chunk, "usage", None))
                # The usage report arrives in a final chunk that carries no
                # choices. Skipping every choice-less chunk would throw away the
                # only token counts the stream ever reports.
                if not chunk.choices:
                    if usage is not None:
                        yield StreamChunk(
                            text="",
                            raw=chunk,
                            usage=usage,
                            model=self._response_model(chunk),
                            provider=self._provider_name,
                        )
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield StreamChunk(
                        text=delta.content,
                        raw=chunk,
                        usage=usage,
                        model=self._response_model(chunk),
                        provider=self._provider_name,
                    )
        except Exception as exc:
            raise ProviderError(str(exc), exc) from exc
