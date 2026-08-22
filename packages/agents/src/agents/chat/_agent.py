"""The conversational agent: a question in, a stream of events out.

Two phases, and the split is deliberate. The tool loop gathers evidence and does
not stream — `LLMProvider.generate_stream` takes no tools, so there is no
streaming tool-call path to use. Then one streaming call turns the evidence the
agent selected into Swedish prose.

Carrying the evidence in a single synthesis prompt rather than in the loop is
what keeps it affordable: a passage placed in the loop is re-sent on every later
iteration, while one placed here is sent once.

The loop has two ways to end, because a conversation has two kinds of message in
it. `answer` ends a turn on evidence and hands it to synthesis;
`reply_from_context` ends a turn that needed no evidence — a greeting, a
thank-you, "förklara det enklare" — and hands it to a prompt that may build only
on what has already been said. Both stream, so a caller has one shape to
forward.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import ai
from ai import agent_run_scope, interaction_scope
from ai.dtos import (
    ChunkContext,
    DirectReplyRequest,
    SynthesizeRequest,
    TabularEvidence,
)
from ai.prompts import CHAT_ORCHESTRATION, render
from llm_core import (
    LLMProvider,
    MaxIterationsError,
    Message,
    ToolCall,
    ToolCallFinished,
    ToolCallStarted,
    ToolExecutionError,
    ToolLoopFinished,
    tool_loop,
)

from agents.chat._dtos import (
    EXCERPT_MAX_CHARS,
    AgentEvent,
    ChatAgentRequest,
    ChatTool,
    DoneEvent,
    ErrorEvent,
    ProgressLabel,
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
            return {"cited_chunks": len(arguments.get("chunk_ids") or [])}
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


def _label_for_result(
    tool: ChatTool, arguments: dict[str, Any], status: ToolStatus
) -> ProgressLabel:
    """The label a finished call reports under.

    Only search differs from its call label: a declined filter is a step of its
    own to a reader — the agent is about to go and read the vocabulary — and
    `search.filtered` would describe a search that never ran.
    """
    if tool is ChatTool.SEARCH_DECISIONS and status is ToolStatus.REFUSED:
        return ProgressLabel.SEARCH_REFUSED
    return label_for_call(tool, arguments)


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
                decision_date=str(decision.decision_date)
                if decision and decision.decision_date
                else None,
                decision_outcome=decision.decision_outcome if decision else None,
                # Ordering is the agent's selection order; there is no fused
                # score left to carry by this point.
                score=0.0,
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
    """One reference per cited decision, first selected passage winning.

    Deduplicated by document because a reader wants the decisions the answer
    rests on, not every passage that happened to match.
    """
    if state.selection is None:
        return []
    seen: set[uuid.UUID] = set()
    sources: list[SourceReference] = []
    for handle in state.selection.chunk_handles:
        record = state.chunks.get(handle)
        if record is None or record.document_id in seen:
            continue
        seen.add(record.document_id)
        decision_handle = state.handle_by_document.get(record.document_id)
        decision = state.decisions.get(decision_handle or "")
        sources.append(
            SourceReference(
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


def _messages_for(request: ChatAgentRequest) -> list[Message]:
    return render(
        CHAT_ORCHESTRATION,
        {
            "question": request.question,
            "today": datetime.now(UTC).date().isoformat(),
            "conversation_history": _format_history(request.history),
        },
    )


def _call_event(call: ToolCall) -> ToolCallEvent:
    tool = ChatTool(call.name)
    return ToolCallEvent(
        id=call.id,
        tool=tool,
        label=label_for_call(tool, call.arguments),
        detail=_detail_for_call(tool, call.arguments),
    )


def _result_event(call: ToolCall, result: Any) -> ToolResultEvent:
    tool = ChatTool(call.name)
    status = _status_for_result(result)
    return ToolResultEvent(
        id=call.id,
        tool=tool,
        label=_label_for_result(tool, call.arguments, status),
        status=status,
        detail=_detail_for_result(tool, result),
    )


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(none)"
    return "\n".join(
        f"{entry.get('role', 'user')}: {entry.get('content', '')}" for entry in history
    )


async def run_chat_agent(
    request: ChatAgentRequest,
    toolset: ChatToolset,
    *,
    llm_provider: LLMProvider | None = None,
    reader_provider: LLMProvider | None = None,
    settings: ChatAgentSettings | None = None,
) -> AsyncIterator[AgentEvent]:
    """Answer `request.question` from the corpus, streaming progress then prose.

    Never raises for a question it cannot answer: a failure ends the stream with
    an `ErrorEvent`, so a caller has one shape to handle rather than two. An
    `ErrorEvent` is terminal — no `DoneEvent` follows it.
    """
    settings = settings or get_chat_agent_settings()
    tools, executors, state = build_chat_tools(
        toolset, settings, reader_provider=reader_provider
    )

    # Inherits the interaction the API opened, and mints one only when there is
    # no caller to inherit from — a `scripts/run_agent.py` case, or a test. The
    # `prompt` key is what attributes these records to a prompt version; every
    # other call site sets one.
    with (
        interaction_scope(
            source=_SOURCE, prompt=CHAT_ORCHESTRATION.name
        ) as interaction_id,
        agent_run_scope(),
    ):
        logger.info("Chat agent interaction %s", interaction_id)

        try:
            async for event in tool_loop(
                _messages_for(request),
                tools,
                executors,
                provider=llm_provider,
                max_iterations=settings.chat_agent_max_iterations,
                terminal_tools={ChatTool.ANSWER, ChatTool.REPLY_FROM_CONTEXT},
            ):
                match event:
                    case ToolCallStarted(call=call):
                        yield _call_event(call)
                    case ToolCallFinished(call=call, result=result):
                        if ChatTool(call.name) is ChatTool.QUERY_CORPUS and isinstance(
                            result, dict
                        ):
                            # Before the result event, so a client that renders
                            # the query can do so while the label is on screen.
                            yield _sql_event(result, state)
                        yield _result_event(call, result)
                    case ToolLoopFinished():
                        pass
        except MaxIterationsError:
            logger.warning(
                "Chat agent %s exhausted its iteration budget", interaction_id
            )
            # An exhausted loop is not necessarily empty-handed: if the agent
            # gathered evidence but never called answer, there is nothing to
            # synthesize from, so this is terminal either way.
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return
        except ToolExecutionError:
            # An executor raised rather than returning an error result, which
            # means a defect here and not a bad tool call — the tools turn every
            # expected failure into a tool result on purpose.
            logger.exception("Chat agent %s tool executor failed", interaction_id)
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return
        except Exception:
            logger.exception("Chat agent %s failed", interaction_id)
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return

        if state.direct_reply is not None:
            # The turn gathered nothing because nothing was needed — a greeting,
            # a thank-you, a question about the previous answer. Checked before
            # the evidence gate, which would otherwise answer "tack" with "I
            # found nothing in the decisions".
            reply = DirectReplyRequest(
                question=request.question,
                conversation_history=request.history,
                notes=state.direct_reply.notes,
            )
            try:
                async for token in ai.reply_from_context(reply, provider=llm_provider):
                    yield TokenEvent(text=token)
            except Exception:
                logger.exception("Chat agent %s direct reply failed", interaction_id)
                yield ErrorEvent(message=_FAILURE_MESSAGE)
                return

            # An empty sources list, and it is the truthful one: this answer
            # rests on the conversation, not on any decision.
            yield SourcesEvent(sources=[])
            yield DoneEvent()
            return

        if not _has_evidence(state):
            # The honest answer to a question the corpus does not address. Said
            # plainly rather than by asking a model to improvise around nothing.
            yield TokenEvent(text=_NO_EVIDENCE_MESSAGE)
            yield SourcesEvent(sources=[])
            yield DoneEvent()
            return

        synthesis = SynthesizeRequest(
            question=request.question,
            chunks=_selected_chunk_contexts(state),
            conversation_history=request.history,
            readings=list(state.readings),
            tabular=_tabular_evidence(state),
            notes=state.selection.notes if state.selection else "",
        )

        try:
            async for token in ai.synthesize_answer(synthesis, provider=llm_provider):
                yield TokenEvent(text=token)
        except Exception:
            logger.exception("Chat agent %s synthesis failed", interaction_id)
            yield ErrorEvent(message=_FAILURE_MESSAGE)
            return

        yield SourcesEvent(sources=_sources(state))
        yield DoneEvent()
