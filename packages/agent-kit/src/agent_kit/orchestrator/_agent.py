"""`run_agent`: the plan → execute → synthesize loop, domain-free.

Three phases, and the split is deliberate — it puts the strong model where the
reasoning is hard and a smaller one where the work is mechanical, and it keeps
the gathered evidence out of the tool loop so it is sent to the writer once
rather than re-sent on every iteration.

1. Plan. One call on `plan_provider` reads the question — with the conversation's
   carry-over blob in front of it — and either writes a direct reply or hands a
   strategy to the executor by calling the plan tool.
2. Execute. The tool loop gathers evidence with the host's tools on
   `executor_provider`, a smaller model, carrying the strategy, and ends on a
   terminal tool.
3. Synthesize. The host's `synthesize` streams the answer from the evidence the
   executor selected.

The evidence itself lives in the host's own object (the executors close over it,
and it is handed in as `evidence`); the orchestrator only holds a typed handle
so it can pass it to `synthesize` and surface it once as an `EvidenceEvent`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from llm_core import (
    LLMProvider,
    MaxIterationsError,
    Scratchpad,
    ToolCallFinished,
    ToolCallStarted,
    ToolDefinition,
    ToolExecutionError,
    ToolExecutor,
    ToolLoopFinished,
    run_tool_loop,
    tool_loop,
    trace_context,
)

from agent_kit.context import ContextStore, JsonBlob
from agent_kit.orchestrator._dtos import (
    AgentRequest,
    ExecutionPhase,
    PlanPhase,
    ScratchpadCodec,
)
from agent_kit.orchestrator._events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    EvidenceEvent,
    PlanReplyEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolStatus,
)
from agent_kit.tracing import agent_run_scope, interaction_scope

logger = logging.getLogger(__name__)

__all__ = ["run_agent"]

# A generic, safe-to-surface failure message. A host that wants its own wording
# replaces it when mapping the `ErrorEvent`.
_FAILURE_MESSAGE = "The request could not be completed."


async def _inert(**_arguments: Any) -> dict[str, Any]:
    """The plan tool's executor. The plan is read off the call, not from this."""
    return {"ok": True}


def _tool_status(result: Any) -> ToolStatus:
    """OK unless the result is a tool-authored error dict.

    The convention a tool uses to decline without raising: a dict with `error`,
    and `refused` true when the decline was on policy rather than a fault.
    """
    if not isinstance(result, dict) or "error" not in result:
        return ToolStatus.OK
    return ToolStatus.REFUSED if result.get("refused") else ToolStatus.ERROR


def _persistence_ready(
    context_store: ContextStore | None,
    conversation_id: str | None,
    scratchpad: Scratchpad[Any] | None,
    codec: ScratchpadCodec[Any] | None,
) -> bool:
    """Whether all four pieces the scratchpad carry-over needs are wired."""
    return (
        context_store is not None
        and conversation_id is not None
        and scratchpad is not None
        and codec is not None
    )


async def _persist_scratchpad(
    context_store: ContextStore,
    conversation_id: str,
    scratchpad: Scratchpad[Any],
    codec: ScratchpadCodec[Any],
) -> None:
    """Store the whole pad under this conversation, for the next turn to restore."""
    await context_store.set(
        conversation_id,
        {"scratchpad": scratchpad.dump(codec.encode, cap=codec.cap)},
    )


async def run_agent[E](
    request: AgentRequest,
    *,
    tools: list[ToolDefinition],
    executors: dict[str, ToolExecutor],
    evidence: E,
    plan: PlanPhase,
    execution: ExecutionPhase,
    synthesize: Callable[[AgentRequest, E], AsyncIterator[str]],
    plan_provider: LLMProvider | None = None,
    executor_provider: LLMProvider | None = None,
    source: str = "agent",
    context_store: ContextStore | None = None,
    conversation_id: str | None = None,
    scratchpad: Scratchpad[Any] | None = None,
    scratchpad_codec: ScratchpadCodec[Any] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Answer `request`, streaming progress events then answer tokens.

    Never raises for a question it cannot answer: a failure ends the stream with
    an `ErrorEvent`, so a caller has one shape to handle. `executor_provider`
    falls back to `plan_provider` when unset, so a single-model run works.

    When a `scratchpad` is given it is the turn's working memory: the executors
    write it (they close over it), the execute loop pins its board into the model
    every iteration, and the host's `synthesize` reads it. When `context_store`,
    `conversation_id` and `scratchpad_codec` are all also given, the pad is
    restored from the store before planning and the whole pad is persisted before
    the terminal event — so a later turn recalls what this one gathered, and the
    planner is shown its shorthand. The pad is usually the same object passed as
    `evidence`; they are separate parameters only because `evidence` is opaque
    (`E`) while the pad must be typed for the board and persistence.
    """
    # The executor loop runs on the smaller model when one is wired; without it
    # the whole turn is one model, which is what a single-provider run does.
    loop_provider = executor_provider or plan_provider

    with (
        interaction_scope(source=source, prompt=execution.prompt_name) as interaction_id,
        agent_run_scope(),
    ):
        persist = _persistence_ready(
            context_store, conversation_id, scratchpad, scratchpad_codec
        )

        blob: JsonBlob = {}
        if context_store is not None and conversation_id is not None:
            blob = await context_store.get(conversation_id)
        # Restore the pad from the store before the plan sees it, so an earlier
        # turn's entries are recallable this turn and the planner is shown their
        # shorthand. `persist` guarantees the codec below is not None.
        if persist:
            assert scratchpad is not None and scratchpad_codec is not None
            scratchpad.restore(blob.get("scratchpad", {}), scratchpad_codec.decode)

        # Phase 1 — plan. One call, traced on its own source so planning cost is
        # separable from executing.
        try:
            with trace_context(source=plan.source, prompt=plan.prompt_name):
                plan_result = await run_tool_loop(
                    plan.build_messages(request, tools, blob),
                    [plan.plan_tool],
                    {plan.plan_tool.name: _inert},
                    provider=plan_provider,
                    max_iterations=1,
                    terminal_tools={plan.plan_tool.name},
                )
        except Exception:
            logger.exception("Agent %s planning failed", interaction_id)
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return

        strategy = plan.read_plan(plan_result.message)
        if strategy is None:
            # A direct reply: the plan step answered from the conversation itself.
            yield PlanReplyEvent(text=plan_result.message.content)
            if persist:
                assert context_store is not None and conversation_id is not None
                assert scratchpad is not None and scratchpad_codec is not None
                await _persist_scratchpad(
                    context_store, conversation_id, scratchpad, scratchpad_codec
                )
            yield DoneEvent()
            return

        # Phase 2 — execute. The tool loop, carrying the strategy, on the smaller
        # model.
        try:
            async for event in tool_loop(
                execution.build_messages(request, tools, strategy),
                tools,
                executors,
                provider=loop_provider,
                max_iterations=execution.max_iterations,
                terminal_tools=execution.terminal_tools,
                scratchpad=scratchpad,
            ):
                match event:
                    case ToolCallStarted(call=call):
                        yield ToolCallEvent(
                            id=call.id, name=call.name, arguments=call.arguments
                        )
                    case ToolCallFinished(call=call, result=result):
                        yield ToolResultEvent(
                            id=call.id,
                            name=call.name,
                            arguments=call.arguments,
                            status=_tool_status(result),
                            result=result,
                        )
                    case ToolLoopFinished():
                        # The loop's own result is carried in `evidence`, which
                        # the executors populated; nothing to forward here.
                        pass
        except MaxIterationsError:
            logger.warning("Agent %s exhausted its iteration budget", interaction_id)
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return
        except ToolExecutionError:
            # An executor raised rather than returning an error result — a defect
            # here, not a bad tool call.
            logger.exception("Agent %s tool executor failed", interaction_id)
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return
        except Exception:
            logger.exception("Agent %s execution failed", interaction_id)
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return

        # Phase 3 — synthesize. The evidence is surfaced once, before the first
        # token that might cite it, then the answer streams. The host's
        # `synthesize` decides what a turn with no evidence says.
        yield EvidenceEvent(evidence=evidence)
        try:
            async for token in synthesize(request, evidence):
                yield TokenEvent(text=token)
        except Exception:
            logger.exception("Agent %s synthesis failed", interaction_id)
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return

        if persist:
            assert context_store is not None and conversation_id is not None
            assert scratchpad is not None and scratchpad_codec is not None
            await _persist_scratchpad(
                context_store, conversation_id, scratchpad, scratchpad_codec
            )
        yield DoneEvent()
