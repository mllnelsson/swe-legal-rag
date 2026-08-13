from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from llm_core._config import LLMConfig, create_provider
from llm_core._exceptions import MaxIterationsError, ToolExecutionError
from llm_core._protocol import LLMProvider
from llm_core._tracing import (
    LLMOperation,
    trace_chunk,
    trace_context,
    trace_response,
    traced_call,
)
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


async def _generate_traced(
    p: LLMProvider,
    messages: list[Message],
    operation: LLMOperation,
    *,
    tools: list[ToolDefinition] | None = None,
    response_schema: type[BaseModel] | None = None,
) -> LLMResponse:
    """One provider round-trip, traced whether it succeeds or fails."""
    with traced_call(operation, messages) as trace:
        response = await p.generate(
            messages, tools=tools, response_schema=response_schema
        )
        trace_response(trace, response)
        return response


async def generate(
    messages: list[Message],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
) -> LLMResponse:
    p = _resolve_provider(provider, config)
    return await _generate_traced(p, messages, LLMOperation.generate)


async def generate_structured[T: BaseModel](
    messages: list[Message],
    response_model: type[T],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
) -> T:
    """Generate and parse into `response_model`, whose type flows to the caller.

    Generic so callers get the model they asked for rather than a bare
    `BaseModel` they must re-narrow with a cast or an assert.
    """
    p = _resolve_provider(provider, config)
    response = await _generate_traced(
        p,
        messages,
        LLMOperation.generate_structured,
        response_schema=response_model,
    )
    # The trace is already closed and marked successful: the call was made and
    # billed, and a schema violation below is a caller-side failure, not a
    # provider one. The record holds the exact text that failed to parse, which
    # is the only thing worth having when debugging it.
    return response_model.model_validate_json(response.message.content)


async def generate_stream(
    messages: list[Message],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
) -> AsyncGenerator[str, None]:
    p = _resolve_provider(provider, config)
    with traced_call(LLMOperation.generate_stream, messages) as trace:
        stream = await p.generate_stream(messages)
        async for chunk in stream:
            trace_chunk(trace, chunk)
            # Usage arrives on a text-less chunk; forwarding it would surface
            # as an empty token to the consumer.
            if chunk.text:
                yield chunk.text


async def tool_loop(
    messages: list[Message],
    tools: list[ToolDefinition],
    executors: dict[str, ToolExecutor],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    terminal_tools: set[str] | None = None,
    on_tool_call: ToolCallCallback | None = None,
    on_tool_result: ToolResultCallback | None = None,
) -> ToolLoopResult:
    """Drive the model until it stops calling tools, or calls a terminal one.

    `terminal_tools` names tools whose call ends the run. Without it a loop ends
    only when the model happens to stop calling tools, which leaves termination
    incidental and the final message throwaway prose. Naming a terminal tool
    makes the ending deliberate and the handoff machine-readable: the tool's
    arguments are the result the caller wanted.
    """
    p = _resolve_provider(provider, config)
    history = list(messages)
    terminal = terminal_tools or set()

    for iteration in range(1, max_iterations + 1):
        # One record per iteration: every pass through the loop is its own
        # billed API call, and collapsing them would hide the cost of a loop
        # that took ten turns to answer.
        with trace_context(tool_loop_iteration=iteration):
            response = await _generate_traced(
                p, history, LLMOperation.tool_loop, tools=tools
            )

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

            if tc.name in terminal:
                # The assistant message is returned rather than the tool result
                # because it carries the terminal call's arguments, which are
                # what the caller came for. Any later call in the same turn is
                # left unexecuted — the model has said it is done — so `history`
                # can end on an assistant message with an unanswered tool call
                # and is not safe to resume a provider round-trip with.
                return ToolLoopResult(
                    message=response.message,
                    history=history,
                    iterations=iteration,
                )

    raise MaxIterationsError(f"Tool loop exceeded {max_iterations} iterations")
