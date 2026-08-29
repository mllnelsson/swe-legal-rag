"""The conversational agent: a question in, a stream of events out.

Three phases, and the split is deliberate — it puts the strong model where the
reasoning is hard and a smaller one where the work is mechanical.

1. Plan. One call on the strong `llm_provider` reads the question and either
   writes a direct reply — a greeting, a thank-you, "förklara det enklare", a
   follow-up the history already answers — or hands a plan to the executor by
   calling `begin_research`. The hard part of a turn is reading what is being
   asked and choosing an approach, and it is done here, once.
2. Execute. The tool loop gathers evidence with tools on `executor_provider`, a
   smaller model, carrying the plan. It does not stream — `generate_stream` takes
   no tools — and ends by calling `answer`.
3. Synthesize. One streaming call on the strong model turns the evidence the
   executor selected into Swedish prose.

Carrying the evidence in a single synthesis prompt rather than in the loop is
what keeps it affordable: a passage placed in the loop is re-sent on every later
iteration, while one placed here is sent once. The direct reply of phase 1
arrives whole rather than token by token, which for two sentences costs nothing
and saves the loop entirely.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import ai
from ai.dtos import (
    ChunkContext,
    PassageNote,
    SynthesizeRequest,
    TabularEvidence,
)
from ai.prompts import CHAT_ORCHESTRATION, CHAT_PLAN, render, render_tool_index
from llm_core import (
    LLMProvider,
    Message,
    ToolCall,
    ToolDefinition,
)

from agent_kit import (
    AgentRequest,
    ContextStore,
    ExecutionPhase,
    JsonBlob,
    PlanPhase,
    run_agent,
)
from agent_kit.orchestrator import DoneEvent as GenericDoneEvent
from agent_kit.orchestrator import ErrorEvent as GenericErrorEvent
from agent_kit.orchestrator import EvidenceEvent, PlanReplyEvent
from agent_kit.orchestrator import TokenEvent as GenericTokenEvent
from agent_kit.orchestrator import ToolCallEvent as GenericToolCallEvent
from agent_kit.orchestrator import ToolResultEvent as GenericToolResultEvent

from agents.chat._dtos import (
    EXCERPT_MAX_CHARS,
    AgentEvent,
    ChatAgentRequest,
    ChatTool,
    DoneEvent,
    ErrorEvent,
    SourceReference,
    SourcesEvent,
    SqlEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolStatus,
)
from agents.chat._protocols import ChatToolset
from agents.chat._tools import ChatState, build_chat_tools, label_for_call
from agents.config import ChatAgentSettings, get_chat_agent_settings

logger = logging.getLogger(__name__)

__all__ = ["run_chat_agent"]

_SOURCE = "agents.chat"

# What the client is told when the run fails. Deliberately generic: the stream
# has already started, so this reaches a user, and provider errors are not for
# them to read.
_FAILURE_MESSAGE = "Ett fel uppstod när frågan besvarades."
_NO_EVIDENCE_MESSAGE = (
    "Jag hittade inget i besluten som besvarar frågan. Pröva att formulera om "
    "den eller att fråga om ett annat ämne."
)

# The plan step runs on the strong model ahead of the loop and is traced apart
# from it, so a turn's cost splits into planning, executing and writing.
_PLAN_SOURCE = "agents.chat.plan"
_BEGIN_RESEARCH = "begin_research"

# The plan step's only tool. Calling it is the signal to research; the plan rides
# on the call's arguments and is read straight off the terminal message, so
# `_begin_research` does no work and the executor loop takes over from there.
_BEGIN_RESEARCH_TOOL = ToolDefinition(
    name=_BEGIN_RESEARCH,
    summary="hand a research plan to the executor",
    description=(
        "Call once to begin research. Pass a short plan in English stating the "
        "intent, the approach and any cautions. The executor holds the tools and "
        "carries the plan out."
    ),
    parameters={
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": (
                    "A short research plan in English: the intent, the approach "
                    "and any cautions."
                ),
            }
        },
        "required": ["plan"],
    },
)


def _plan_from(message: Message) -> str | None:
    """The plan the plan step produced, or None when it replied directly.

    A `begin_research` call carries the plan on its arguments; a message that
    called no tool is a direct reply — a greeting, a follow-up the history
    already answers — and there is no plan to carry.
    """
    for call in message.tool_calls:
        if call.name == _BEGIN_RESEARCH:
            plan = call.arguments.get("plan")
            return plan if isinstance(plan, str) else ""
    return None


def _detail_for_call(tool: ChatTool, arguments: dict[str, Any]) -> dict[str, Any]:
    """Structured facts about a call, never a sentence.

    The client turns the label into words; this is only what it may use to
    enrich them.
    """
    match tool:
        case ChatTool.SEARCH_DECISIONS:
            document_filter = arguments.get("document_filter") or {}
            return {
                "has_filter": bool(document_filter),
                "filter_fields": sorted(document_filter),
                "include_appendices": bool(arguments.get("include_appendices")),
            }
        case ChatTool.READ_DECISION | ChatTool.INSPECT_DECISION:
            return {"document_id": arguments.get("document_id")}
        case ChatTool.ANSWER:
            return {"cited_chunks": len(arguments.get("annotations") or [])}
        case _:
            return {}


def _detail_for_result(tool: ChatTool, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    match tool:
        case ChatTool.SEARCH_DECISIONS:
            return {
                "decision_count": result.get("decision_count", 0),
                "widened_to_appendices": bool(result.get("widened_to_appendices")),
            }
        case ChatTool.QUERY_CORPUS:
            return {
                "answered": bool(result.get("answered")),
                "row_count": result.get("row_count", 0),
            }
        case ChatTool.READ_DECISION:
            return {"document_id": result.get("document_id")}
        case _:
            return {}


def _status_for_result(result: Any) -> ToolStatus:
    if not isinstance(result, dict) or "error" not in result:
        return ToolStatus.OK
    return ToolStatus.REFUSED if result.get("refused") else ToolStatus.ERROR


def _sql_event(result: dict[str, Any], state: ChatState) -> SqlEvent:
    """The query behind a count, with the whole attempt trail.

    `attempts` comes off the SQL agent's own result rather than the tool
    payload: it is what shows a reader that the agent grounded a predicate
    before committing to the query that produced the answer.
    """
    attempts = state.tabular.attempts if state.tabular is not None else []
    return SqlEvent(
        answered=bool(result.get("answered")),
        sql=result.get("sql"),
        columns=result.get("columns") or [],
        rows=result.get("rows") or [],
        row_count=result.get("row_count") or 0,
        truncated=bool(result.get("truncated")),
        assumptions=result.get("assumptions") or [],
        attempts=list(attempts),
    )


def _selected_chunk_contexts(state: ChatState) -> list[ChunkContext]:
    """The selected passages, in the order the agent named them.

    The handle travels with each one: it is what the writer marks a claim with
    and what the client resolves that mark back to a source.
    """
    if state.selection is None:
        return []
    contexts: list[ChunkContext] = []
    for handle in state.selection.chunk_handles:
        record = state.chunks.get(handle)
        if record is None:
            continue
        decision_handle = state.handle_by_document.get(record.document_id)
        decision = state.decisions.get(decision_handle or "")
        contexts.append(
            ChunkContext(
                chunk_text=record.chunk.text,
                case_number=(decision.case_number if decision else None) or handle,
                handle=handle,
                section=record.chunk.section,
                appendix_label=record.chunk.appendix_label,
            )
        )
    return contexts


def _tabular_evidence(state: ChatState) -> TabularEvidence | None:
    result = state.tabular
    if result is None or not result.answered or result.sql is None:
        return None
    return TabularEvidence(
        sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        assumptions=result.assumptions,
    )


def _sources(state: ChatState) -> list[SourceReference]:
    """One reference per cited passage, in the order the agent selected them.

    Not deduplicated by decision. The answer marks each claim with a passage
    handle, so every handle it can name has to be resolvable — collapsing two
    passages of one decision would leave one of those marks pointing at
    nothing. A client that wants the decisions groups by `document_id`.
    """
    if state.selection is None:
        return []
    sources: list[SourceReference] = []
    for handle in state.selection.chunk_handles:
        record = state.chunks.get(handle)
        if record is None:
            continue
        decision_handle = state.handle_by_document.get(record.document_id)
        decision = state.decisions.get(decision_handle or "")
        sources.append(
            SourceReference(
                handle=handle,
                document_id=record.document_id,
                case_number=decision.case_number if decision else None,
                decision_date=decision.decision_date if decision else None,
                decision_outcome=decision.decision_outcome if decision else None,
                category=decision.category if decision else None,
                excerpt=record.chunk.text[:EXCERPT_MAX_CHARS],
                section=record.chunk.section,
                appendix_label=record.chunk.appendix_label,
            )
        )
    return sources


def _has_evidence(state: ChatState) -> bool:
    return bool(
        _selected_chunk_contexts(state) or state.readings or _tabular_evidence(state)
    )


def _plan_messages_for(
    request: ChatAgentRequest, tools: list[ToolDefinition], context: JsonBlob
) -> list[Message]:
    """The plan step's prompt.

    Shown the executor's tools so the plan it writes is realistic, though the
    only tool it holds is `begin_research`. The carry-over `context` blob — the
    running notes an earlier turn left, `{}` on the first — is rendered into it
    so the planner sees the conversation's state before it chooses an approach.
    """
    return render(
        CHAT_PLAN,
        {
            "question": request.question,
            "today": datetime.now(UTC).date().isoformat(),
            "conversation_history": _format_history(request.history),
            "tools": render_tool_index(tools),
            "context": json.dumps(context, ensure_ascii=False),
        },
    )


def _executor_messages_for(
    request: ChatAgentRequest, tools: list[ToolDefinition], plan: str
) -> list[Message]:
    return render(
        CHAT_ORCHESTRATION,
        {
            "question": request.question,
            "today": datetime.now(UTC).date().isoformat(),
            "conversation_history": _format_history(request.history),
            # Generated from the definitions the loop is about to be given, so
            # the prompt cannot name an argument the executors lack.
            "tools": render_tool_index(tools),
            # The strategy the plan step set. The executor carries it out.
            "plan": plan,
        },
    )


def _tool_or_none(name: str) -> ChatTool | None:
    try:
        return ChatTool(name)
    except ValueError:
        return None


def _call_event(tool: ChatTool, call: ToolCall) -> ToolCallEvent:
    return ToolCallEvent(
        id=call.id,
        tool=tool,
        label=label_for_call(tool, call.arguments),
        detail=_detail_for_call(tool, call.arguments),
    )


def _result_event(tool: ChatTool, call: ToolCall, result: Any) -> ToolResultEvent:
    return ToolResultEvent(
        id=call.id,
        tool=tool,
        # The same label the call reported. A declined filter is not a step of
        # its own: `status` already says it was refused, and a second label for
        # the same tool made a client choose between two ways to learn one fact.
        label=label_for_call(tool, call.arguments),
        status=_status_for_result(result),
        detail=_detail_for_result(tool, result),
    )


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(none)"
    return "\n".join(
        f"{entry.get('role', 'user')}: {entry.get('content', '')}" for entry in history
    )


def chat_context_carry(
    blob: JsonBlob, _request: AgentRequest, state: ChatState
) -> JsonBlob:
    """The carry-over the chat agent leaves for the next turn.

    Deterministic and free — read off the passages this turn cited, not from a
    model call. It accumulates the case numbers the conversation has surfaced so
    the next turn's planner has continuity ("we have already looked at Mål
    12/2024") without re-retrieving. A chatty turn cites nothing and carries the
    blob forward unchanged.

    The default a caller passes as `run_chat_agent(..., derive_context=...)`; a
    caller that wants a richer carry-over (an LLM-written running brief, say)
    passes its own instead.
    """
    seen = {
        case for case in blob.get("cases_discussed", []) if isinstance(case, str)
    }
    seen.update(
        source.case_number for source in _sources(state) if source.case_number
    )
    return {"cases_discussed": sorted(seen)}


def _synthesis_request(
    request: ChatAgentRequest, state: ChatState
) -> SynthesizeRequest:
    """The evidence bundle the writer streams from, read out of the run's state."""
    return SynthesizeRequest(
        question=request.question,
        chunks=_selected_chunk_contexts(state),
        conversation_history=request.history,
        readings=list(state.readings),
        tabular=_tabular_evidence(state),
        annotations=[
            PassageNote(handle=note.handle, carries=note.carries, caution=note.caution)
            for note in (state.selection.annotations if state.selection else [])
        ],
        gaps=list(state.selection.gaps) if state.selection else [],
    )


async def run_chat_agent(
    request: ChatAgentRequest,
    toolset: ChatToolset,
    *,
    llm_provider: LLMProvider | None = None,
    reader_provider: LLMProvider | None = None,
    executor_provider: LLMProvider | None = None,
    settings: ChatAgentSettings | None = None,
    context_store: ContextStore | None = None,
    derive_context: Callable[[JsonBlob, AgentRequest, ChatState], JsonBlob]
    | None = None,
) -> AsyncIterator[AgentEvent]:
    """Answer `request.question` from the corpus, streaming progress then prose.

    A thin configuration of `agent_kit.run_agent`: this owns the domain — the
    tools, the Swedish prompts, and how the generic progress stream maps onto the
    chat wire events — while the orchestrator owns the plan → execute → synthesize
    control flow, the tracing scopes and the error funnel.

    The plan step on the strong `llm_provider` reads the question and either
    replies directly or hands a plan to the executor loop on `executor_provider`,
    a smaller model that falls back to `llm_provider` when unset (so a single-model
    run and every existing test still work). A final streaming call on
    `llm_provider` writes the Swedish prose.

    Never raises for a question it cannot answer: a failure ends the stream with
    an `ErrorEvent`, which is terminal — no `DoneEvent` follows it.
    """
    settings = settings or get_chat_agent_settings()
    tools, executors, state = build_chat_tools(
        toolset, settings, reader_provider=reader_provider
    )

    # The prompt builders and the writer close over the concretely-typed request,
    # tools and state, so the orchestrator's domain-free callbacks stay untyped by
    # this project's shapes. The plan builder ignores the carry-over blob for now;
    # it is threaded into the prompt when the context store is wired up.
    plan = PlanPhase(
        build_messages=lambda _req, _tools, blob: _plan_messages_for(
            request, tools, blob
        ),
        plan_tool=_BEGIN_RESEARCH_TOOL,
        read_plan=_plan_from,
        prompt_name=CHAT_PLAN.name,
        source=_PLAN_SOURCE,
    )
    execution = ExecutionPhase(
        build_messages=lambda _req, _tools, strategy: _executor_messages_for(
            request, tools, strategy
        ),
        terminal_tools={ChatTool.ANSWER},
        max_iterations=settings.chat_agent_max_iterations,
        prompt_name=CHAT_ORCHESTRATION.name,
    )

    async def _synthesize(
        _req: AgentRequest, _evidence: ChatState
    ) -> AsyncIterator[str]:
        # The honest answer to a question the corpus does not address, said
        # plainly rather than by asking a model to improvise around nothing.
        if not _has_evidence(state):
            yield _NO_EVIDENCE_MESSAGE
            return
        async for token in ai.synthesize_answer(
            _synthesis_request(request, state), provider=llm_provider
        ):
            yield token

    async for event in run_agent(
        request,
        tools=tools,
        executors=executors,
        evidence=state,
        plan=plan,
        execution=execution,
        synthesize=_synthesize,
        plan_provider=llm_provider,
        executor_provider=executor_provider,
        source=_SOURCE,
        context_store=context_store,
        conversation_id=request.conversation_id,
        derive_context=derive_context,
    ):
        match event:
            case PlanReplyEvent(text=text):
                # A direct reply rests on the history, not on any decision, so an
                # empty sources list is the truthful one.
                yield SourcesEvent(sources=[])
                yield TokenEvent(text=text)
            case GenericToolCallEvent(id=cid, name=name, arguments=arguments):
                # A name that is not one of ours has no progress to report.
                if (tool := _tool_or_none(name)) is not None:
                    yield _call_event(
                        tool, ToolCall(id=cid, name=name, arguments=arguments)
                    )
            case GenericToolResultEvent(
                id=cid, name=name, arguments=arguments, result=result
            ):
                if (tool := _tool_or_none(name)) is None:
                    continue
                if tool is ChatTool.QUERY_CORPUS and isinstance(result, dict):
                    # Before the result event, so a client that renders the
                    # query can do so while the label is on screen.
                    yield _sql_event(result, state)
                yield _result_event(
                    tool, ToolCall(id=cid, name=name, arguments=arguments), result
                )
            case EvidenceEvent():
                # Before the prose, not after it. The answer marks its claims
                # with passage handles as it streams, and a mark a client cannot
                # resolve yet is a citation it renders as nothing. Empty in the
                # no-evidence case — the same list a direct reply sends.
                yield SourcesEvent(sources=_sources(state))
            case GenericTokenEvent(text=text):
                yield TokenEvent(text=text)
            case GenericDoneEvent():
                yield DoneEvent()
            case GenericErrorEvent():
                # The orchestrator's failure string is generic; the reader, whose
                # stream has already started, gets this project's message.
                yield ErrorEvent(message=_FAILURE_MESSAGE)
