from __future__ import annotations

import inspect
import json
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
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
from llm_core.scratchpad import Scratchpad

ToolExecutor = Callable[..., Awaitable[Any]]

# Safety bound on the agentic tool-calling loop before giving up.
DEFAULT_MAX_ITERATIONS = 10

# Preamble on the pinned scratchpad board, so the model reads it as its own
# working memory rather than as another turn of conversation.
_BOARD_PREAMBLE = (
    "[scratchpad] Everything gathered so far, refreshed each step. Each line is "
    "key  preview; recall a value by its key rather than fetching it again."
)


def _with_board(history: list[Message], scratchpad: Scratchpad[Any] | None) -> list[Message]:
    """`history` with the pad's current board pinned in front, when there is one.

    Rebuilt every iteration from the live pad and never appended to `history`, so
    the board always reflects the latest state and refreshes in place rather than
    stacking a stale copy on every pass.
    """
    if scratchpad is None:
        return history
    board = scratchpad.render_board()
    if not board:
        return history
    pinned = Message(role=Role.system, content=f"{_BOARD_PREAMBLE}\n{board}")
    return [pinned, *history]


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    message: Message
    history: list[Message]
    iterations: int


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    """The model asked for a tool; the executor has not run yet."""

    call: ToolCall
    history: list[Message]


@dataclass(frozen=True, slots=True)
class ToolCallFinished:
    """The executor returned. `result` is whatever it returned, unserialized."""

    call: ToolCall
    result: Any
    history: list[Message]


@dataclass(frozen=True, slots=True)
class ToolLoopFinished:
    """The run is over. Always the last event, and the only one carrying a result."""

    result: ToolLoopResult


ToolLoopEvent = ToolCallStarted | ToolCallFinished | ToolLoopFinished


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


def _refusal_for_unbindable_call(
    executor: ToolExecutor, call: ToolCall
) -> dict[str, Any] | None:
    """The tool result a call that does not fit its executor comes back as.

    `None` when the call binds — and when the callable cannot report a
    signature at all, a C builtin or an exotic wrapper, where there is nothing
    to check it against and invoking is the only way to find out.

    Executors are called by keyword, so a wrong or missing argument name was
    the one kind of bad call `tool_loop` could not repair from: it raised
    `TypeError`, became a `ToolExecutionError` and ended the run, while every
    refusal an executor makes for itself comes back as an ordinary result the
    model fixes on its next iteration. Binding first puts the two on the same
    footing, and keeps a `TypeError` raised from *inside* an executor a defect.
    """
    try:
        signature = inspect.signature(executor)
    except (TypeError, ValueError):
        return None

    try:
        signature.bind(**call.arguments)
    except TypeError as exc:
        # The valid names are spelled out because `bind` reports only the first
        # thing wrong: given a wrong name *and* a missing one it names the
        # missing one, leaving the model no way to learn which of its arguments
        # was rejected.
        valid = ", ".join(signature.parameters) or "none"
        return {
            "error": f"{call.name}: {exc}. Valid arguments: {valid}.",
            "refused": True,
        }
    return None


async def tool_loop(
    messages: list[Message],
    tools: list[ToolDefinition],
    executors: dict[str, ToolExecutor],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    terminal_tools: set[str] | None = None,
    scratchpad: Scratchpad[Any] | None = None,
) -> AsyncIterator[ToolLoopEvent]:
    """Drive the model until it stops calling tools, or calls a terminal one.

    Yields its progress rather than reporting it through callbacks, so a caller
    that needs to `yield` per step — an SSE generator, say — is an ordinary
    `async for` over this. A generator cannot return a value, so the run's
    result arrives as the final `ToolLoopFinished` event; `run_tool_loop` is the
    convenience for callers that only want that.

    `terminal_tools` names tools whose call ends the run. Without it a loop ends
    only when the model happens to stop calling tools, which leaves termination
    incidental and the final message throwaway prose. Naming a terminal tool
    makes the ending deliberate and the handoff machine-readable: the tool's
    arguments are the result the caller wanted.

    The two endings are both legitimate and a caller must tell them apart:
    `message.tool_calls` is empty when the model chose to answer in prose, and
    carries the terminal call when it chose to finish through a tool.

    Executors are called by keyword, so a call whose arguments do not fit the
    executor's signature comes back to the model as `{"error": ..., "refused":
    True}` rather than raising — the one tool result this loop authors itself.
    An exception from *inside* an executor is still a `ToolExecutionError`: that
    is a defect, and the two must not be confused.

    When a `scratchpad` is given, its board is pinned in front of the history on
    every iteration, refreshed from the live pad — so the model always sees what
    has been gathered without the heavy values being re-sent. The pad is the
    executors' to write (they close over it); this loop only renders it.
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
                p,
                _with_board(history, scratchpad),
                LLMOperation.tool_loop,
                tools=tools,
            )

        history.append(response.message)

        if not response.message.tool_calls:
            yield ToolLoopFinished(
                ToolLoopResult(
                    message=response.message,
                    history=history,
                    iterations=iteration,
                )
            )
            return

        for tc in response.message.tool_calls:
            yield ToolCallStarted(call=tc, history=history)

            if tc.name not in executors:
                raise ToolExecutionError(
                    tc.name, f"No executor registered for tool {tc.name!r}"
                )

            executor = executors[tc.name]
            refusal = _refusal_for_unbindable_call(executor, tc)
            if refusal is not None:
                result: Any = refusal
            else:
                # Binding is what separates the two: a call that does not fit
                # the signature is refused above, so anything raising here came
                # from inside the executor and is a defect.
                try:
                    result = await executor(**tc.arguments)
                except Exception as exc:
                    raise ToolExecutionError(tc.name, str(exc), cause=exc) from exc

            # `ensure_ascii=False`: a tool result on a Swedish corpus is mostly
            # å, ä and ö, and escaping each to \uXXXX inflates the payload ~48%
            # — paid again on every later iteration, since the result stays in
            # the history. The provider sends UTF-8 either way.
            result_str = (
                result
                if isinstance(result, str)
                else json.dumps(result, ensure_ascii=False)
            )

            history.append(
                Message(
                    role=Role.tool_result,
                    content=result_str,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                )
            )

            yield ToolCallFinished(call=tc, result=result, history=history)

            if tc.name in terminal:
                # The assistant message is returned rather than the tool result
                # because it carries the terminal call's arguments, which are
                # what the caller came for. Any later call in the same turn is
                # left unexecuted — the model has said it is done — so `history`
                # can end on an assistant message with an unanswered tool call
                # and is not safe to resume a provider round-trip with.
                yield ToolLoopFinished(
                    ToolLoopResult(
                        message=response.message,
                        history=history,
                        iterations=iteration,
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
    terminal_tools: set[str] | None = None,
    scratchpad: Scratchpad[Any] | None = None,
) -> ToolLoopResult:
    """`tool_loop` for a caller that wants the result and not the progress."""
    result: ToolLoopResult | None = None
    async for event in tool_loop(
        messages,
        tools,
        executors,
        provider=provider,
        config=config,
        max_iterations=max_iterations,
        terminal_tools=terminal_tools,
        scratchpad=scratchpad,
    ):
        if isinstance(event, ToolLoopFinished):
            result = event.result
    # Unreachable: the loop either yields ToolLoopFinished or raises. Asserted
    # rather than cast so a future edit that breaks the invariant says so.
    assert result is not None, "tool_loop ended without a result"
    return result
