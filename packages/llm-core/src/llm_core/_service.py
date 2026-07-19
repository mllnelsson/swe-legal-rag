from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from llm_core._config import LLMConfig, create_provider
from llm_core._exceptions import MaxIterationsError, ToolExecutionError
from llm_core._protocol import LLMProvider
from llm_core._types import LLMResponse, Message, Role, ToolCall, ToolDefinition

ToolExecutor = Callable[..., Awaitable[Any]]
ToolCallCallback = Callable[[ToolCall, list[Message]], Awaitable[None]]
ToolResultCallback = Callable[[ToolCall, Any, list[Message]], Awaitable[None]]

# Safety bound on the agentic tool-calling loop before giving up.
DEFAULT_MAX_ITERATIONS = 10


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    message: Message
    history: list[Message]
    iterations: int


def _resolve_provider(
    provider: LLMProvider | None, config: LLMConfig | None
) -> LLMProvider:
    if provider is not None:
        return provider
    return create_provider(config)


async def generate(
    messages: list[Message],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
) -> LLMResponse:
    return await _resolve_provider(provider, config).generate(messages)


async def generate_structured(
    messages: list[Message],
    response_model: type[BaseModel],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
) -> BaseModel:
    p = _resolve_provider(provider, config)
    response = await p.generate(messages, response_schema=response_model)
    return response_model.model_validate_json(response.message.content)


async def generate_stream(
    messages: list[Message],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
) -> AsyncIterator[str]:
    p = _resolve_provider(provider, config)
    async for chunk in await p.generate_stream(messages):
        yield chunk.text


async def tool_loop(
    messages: list[Message],
    tools: list[ToolDefinition],
    executors: dict[str, ToolExecutor],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    on_tool_call: ToolCallCallback | None = None,
    on_tool_result: ToolResultCallback | None = None,
) -> ToolLoopResult:
    p = _resolve_provider(provider, config)
    history = list(messages)

    for iteration in range(1, max_iterations + 1):
        response = await p.generate(history, tools=tools)

        if not response.message.tool_calls:
            history.append(response.message)
            return ToolLoopResult(
                message=response.message,
                history=history,
                iterations=iteration,
            )

        history.append(response.message)

        for tc in response.message.tool_calls:
            if on_tool_call is not None:
                await on_tool_call(tc, history)

            if tc.name not in executors:
                raise ToolExecutionError(
                    tc.name, f"No executor registered for tool {tc.name!r}"
                )

            try:
                result = await executors[tc.name](**tc.arguments)
            except Exception as exc:
                raise ToolExecutionError(tc.name, str(exc), cause=exc) from exc

            result_str = result if isinstance(result, str) else json.dumps(result)

            history.append(
                Message(
                    role=Role.tool_result,
                    content=result_str,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                )
            )

            if on_tool_result is not None:
                await on_tool_result(tc, result, history)

    raise MaxIterationsError(f"Tool loop exceeded {max_iterations} iterations")
