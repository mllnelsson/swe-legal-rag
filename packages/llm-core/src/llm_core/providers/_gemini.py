from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import TYPE_CHECKING, Any

from llm_core._exceptions import ProviderError
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
    from pydantic import BaseModel

    from llm_core._config import LLMConfig


def _usage_from_gemini(usage_metadata: Any) -> Usage | None:
    if usage_metadata is None:
        return None

    candidates = getattr(usage_metadata, "candidates_token_count", None)
    thoughts = getattr(usage_metadata, "thoughts_token_count", None)

    # Thinking tokens bill at the output rate but are excluded from
    # candidates_token_count, so folding them in is what keeps the cost
    # estimate honest on the 2.5 models.
    if candidates is None and thoughts is None:
        output_tokens = None
    else:
        output_tokens = (candidates or 0) + (thoughts or 0)

    return Usage(
        input_tokens=getattr(usage_metadata, "prompt_token_count", None),
        output_tokens=output_tokens,
        total_tokens=getattr(usage_metadata, "total_token_count", None),
    )


class GeminiProvider:
    def __init__(self, config: LLMConfig) -> None:
        from google import genai

        if not config.gemini_api_key:
            raise ValueError("gemini_api_key is required for GeminiProvider")

        self._client = genai.Client(api_key=config.gemini_api_key)
        self._model = config.model
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens
        self._provider_name = config.provider

    def _split_system(
        self, messages: list[Message]
    ) -> tuple[str | None, list[Message]]:
        if messages and messages[0].role == Role.system:
            return messages[0].content, messages[1:]
        return None, messages

    def _to_gemini_content(self, msg: Message) -> Any:
        from google.genai import types

        match msg.role:
            case Role.user:
                return types.Content(
                    role="user", parts=[types.Part.from_text(text=msg.content)]
                )
            case Role.assistant:
                parts: list[Any] = []
                if msg.content:
                    parts.append(types.Part.from_text(text=msg.content))
                for tc in msg.tool_calls:
                    parts.append(
                        types.Part.from_function_call(name=tc.name, args=tc.arguments)
                    )
                return types.Content(role="model", parts=parts)
            case Role.tool_result:
                return types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=msg.tool_name or "",
                            response={"output": msg.content},
                        )
                    ],
                )
            case Role.system | Role.tool_call:
                # system is stripped by _split_system; tool_call is never a
                # standalone message role here.
                raise ValueError(f"Cannot map role {msg.role!r} to Gemini content")

    def _to_gemini_tools(self, tools: list[ToolDefinition]) -> Any:
        from google.genai import types

        declarations = [
            types.FunctionDeclaration(
                name=t.name,
                description=t.description,
                parameters_json_schema=t.parameters,
            )
            for t in tools
        ]
        return types.Tool(function_declarations=declarations)

    def _from_gemini_response(self, response: Any) -> LLMResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for candidate in response.candidates or []:
            for part in candidate.content.parts or []:
                if part.text:
                    text_parts.append(part.text)
                if part.function_call:
                    fc = part.function_call
                    call_id = fc.id or str(uuid.uuid4())
                    tool_calls.append(
                        ToolCall(
                            id=call_id,
                            name=fc.name or "",
                            arguments=dict(fc.args or {}),
                        )
                    )

        if tool_calls:
            msg = Message(
                role=Role.assistant,
                content="".join(text_parts),
                tool_calls=tuple(tool_calls),
            )
        else:
            msg = Message(role=Role.assistant, content="".join(text_parts))

        return LLMResponse(
            message=msg,
            raw=response,
            usage=_usage_from_gemini(getattr(response, "usage_metadata", None)),
            model=self._response_model(response),
            provider=self._provider_name,
        )

    def _response_model(self, response: Any) -> str:
        """The model version the API says it served, not the one we asked for.

        A name like "gemini-2.5-flash" resolves to a dated build, and cost must
        be attributed to what actually ran.
        """
        return getattr(response, "model_version", None) or self._model

    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        from google.genai import types

        system_instruction, remaining = self._split_system(messages)
        contents = [self._to_gemini_content(m) for m in remaining]

        config_kwargs: dict[str, Any] = {
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            config_kwargs["max_output_tokens"] = self._max_tokens
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction
        if tools:
            config_kwargs["tools"] = [self._to_gemini_tools(tools)]
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = response_schema.model_json_schema()

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            raise ProviderError(str(exc), exc) from exc

        return self._from_gemini_response(response)

    async def generate_stream(
        self,
        messages: list[Message],
    ) -> AsyncIterator[StreamChunk]:
        from google.genai import types

        system_instruction, remaining = self._split_system(messages)
        contents = [self._to_gemini_content(m) for m in remaining]

        config_kwargs: dict[str, Any] = {
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            config_kwargs["max_output_tokens"] = self._max_tokens
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            sdk_stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            raise ProviderError(str(exc), exc) from exc

        return self._iter_stream(sdk_stream)

    async def _iter_stream(self, sdk_stream: Any) -> AsyncGenerator[StreamChunk, None]:
        try:
            async for chunk in sdk_stream:
                usage = _usage_from_gemini(getattr(chunk, "usage_metadata", None))
                # Usage rides along cumulatively and the final report often
                # arrives on a chunk with no text; yielding a text-less chunk is
                # how those counts reach the trace. Consumers skip empty text.
                if not chunk.text and usage is None:
                    continue
                yield StreamChunk(
                    text=chunk.text or "",
                    raw=chunk,
                    usage=usage,
                    model=self._response_model(chunk),
                    provider=self._provider_name,
                )
        except Exception as exc:
            raise ProviderError(str(exc), exc) from exc
