from __future__ import annotations

import inspect
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
# Decides whether a finished call ends the run. It is handed the result as well
# as the call, because a terminal tool that declined has ended nothing — see
# `tool_loop`.
TerminalPredicate = Callable[[ToolCall, Any], bool]

# Safety bound on the agentic tool-calling loop before giving up.
DEFAULT_MAX_ITERATIONS = 10


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    message: Message
    history: list[Message]
    iterations: int


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    """The model asked for a call, and the executor has not run yet."""

    call: ToolCall
    history: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class ToolCallCompleted:
    """The executor returned, and its result is already appended to `history`."""

    call: ToolCall
    result: Any
    history: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class LoopFinished:
    """The last event of every run that does not raise."""

    result: ToolLoopResult


ToolLoopEvent = ToolCallStarted | ToolCallCompleted | LoopFinished


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
    is_terminal: TerminalPredicate | None = None,
) -> AsyncGenerator[ToolLoopEvent, None]:
    """Drive the model until it stops calling tools, or calls a terminal one.

    Yields `ToolCallStarted` and `ToolCallCompleted` around every executed call,
    and `LoopFinished` last. Yielding rather than invoking callbacks is what
    lets a caller that is itself a generator — an SSE endpoint, say — forward
    each step as it happens, instead of running the loop as a task and draining
    a queue the callbacks push to. `run_tool_loop` is there for callers with no
    progress to report.

    `is_terminal` decides which finished call ends the run. Without it a loop
    ends only when the model happens to stop calling tools, which leaves
    termination incidental and the final message throwaway prose. Deciding it
    makes the ending deliberate and the handoff machine-readable: the tool's
    arguments are the result the caller wanted. The predicate is given the
    result as well as the call, because a terminal tool that *declined* has
    ended nothing — the loop has to go on so the model can repair the call.

    Executors are called by keyword, so a call whose arguments do not fit the
    executor's signature comes back to the model as `{"error": ..., "refused":
    True}` rather than raising — the one tool result this loop authors itself.
    An exception from *inside* an executor is still a `ToolExecutionError`: that
    is a defect, and the two must not be confused.

    Nothing is yielded from inside a `trace_context` block: an async generator
    shares its consumer's context, so a context variable set across a yield
    would leak into whatever drives the loop.
    """
    p = _resolve_provider(provider, config)
    history = list(messages)

    for iteration in range(1, max_iterations + 1):
        # One record per iteration: every pass through the loop is its own
        # billed API call, and collapsing them would hide the cost of a loop
        # that took ten turns to answer.
        with trace_context(tool_loop_iteration=iteration):
            response = await _generate_traced(
                p, history, LLMOperation.tool_loop, tools=tools
            )

        history.append(response.message)

        if not response.message.tool_calls:
            yield LoopFinished(
                ToolLoopResult(
                    message=response.message, history=history, iterations=iteration
                )
            )
            return

        for tc in response.message.tool_calls:
            yield ToolCallStarted(call=tc, history=tuple(history))

            if tc.name not in executors:
                raise ToolExecutionError(
                    tc.name, f"No executor registered for tool {tc.name!r}"
                )

            executor = executors[tc.name]
            signature = inspect.signature(executor)
            try:
                signature.bind(**tc.arguments)
            except TypeError as exc:
                # The model named an argument the executor does not have, or
                # left out one it needs. Returned rather than raised: that is a
                # bad call, not a defect here, and it was the only kind of bad
                # call the loop could not repair from. This is the one tool
                # result the loop authors itself.
                #
                # The valid names are spelled out because `bind` reports only
                # the first thing wrong — given a wrong name *and* a missing
                # one it names the missing one, leaving the model no way to
                # learn which of its arguments was rejected.
                valid = ", ".join(signature.parameters) or "none"
                result: Any = {
                    "error": f"{tc.name}: {exc}. Valid arguments: {valid}.",
                    "refused": True,
                }
            else:
                try:
                    result = await executor(**tc.arguments)
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

            yield ToolCallCompleted(call=tc, result=result, history=tuple(history))

            if is_terminal is not None and is_terminal(tc, result):
                # The assistant message is carried out rather than the tool
                # result because it holds the terminal call's arguments, which
                # are what the caller came for. Any later call in the same turn
                # is left unexecuted — the model has said it is done — so
                # `history` can end on an assistant message with an unanswered
                # tool call and is not safe to resume a provider round-trip with.
                yield LoopFinished(
                    ToolLoopResult(
                        message=response.message, history=history, iterations=iteration
                    )
                )
                return

    raise MaxIterationsError(f"Tool loop exceeded {max_iterations} iterations")


async def run_tool_loop(
    messages: list[Message],
    tools: list[ToolDefinition],
    executors: dict[str, ToolExecutor],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    is_terminal: TerminalPredicate | None = None,
) -> ToolLoopResult:
    """Drive a tool loop to completion and return only what it ended with.

    For callers with nothing to report as they go — a batch runner, a sub-agent
    whose progress never reaches a reader — so that they need not iterate events
    they would only discard.
    """
    async for event in tool_loop(
        messages,
        tools,
        executors,
        provider=provider,
        config=config,
        max_iterations=max_iterations,
        is_terminal=is_terminal,
    ):
        match event:
            case LoopFinished(result=result):
                return result
            case _:
                continue
    # Unreachable: the loop either yields `LoopFinished` or raises.
    raise MaxIterationsError(f"Tool loop exceeded {max_iterations} iterations")
