"""The tools the conversational agent is given, and the state that bounds them.

Two ideas carry most of the weight here.

**Grounding.** `documents.category` and `documents.decision_outcome` hold free
text, so a guessed filter value matches nothing — and the deterministic search
stops on an empty filter rather than widening, which turns a guess into a
confident empty answer. A filter touching one of those columns is therefore
refused until the agent has actually read the values, exactly as `run_sql`
refuses an ungrounded predicate. The prompt asks for the same thing, but a
prompt is a request and this is a precondition.

**Handles.** Chunks and decisions are addressed as `c1`, `d2` rather than by
UUID. A mid-tier model transcribes a short handle reliably and a UUID
unreliably, and an unknown handle is detectable — it comes back as a refusal
listing the valid ones, instead of silently selecting nothing.

A refusal is not an error. It is returned to the model as a tool result, so the
next iteration repairs itself through the loop's ordinary path.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from ai.dtos import DecisionReading
from llm_core import LLMProvider, ToolDefinition
from shared.dtos.search import DocumentFilter
from shared.enums import ChunkSection

from agents.chat._dtos import (
    ChatTool,
    DecisionText,
    PassageNote,
    ProgressLabel,
    ReadingSelection,
    SearchedChunk,
    SearchedDecision,
)
from agents.chat._protocols import ChatToolset
from agents.chat._reader import read_decision_text
from agents.config import ChatAgentSettings
from agents.sql._dtos import SqlAgentResult

logger = logging.getLogger(__name__)

__all__ = [
    "ChatState",
    "build_chat_tools",
    "label_for_call",
    "FREE_TEXT_FILTER_FIELDS",
]

# Filter fields whose values are free text rather than a controlled vocabulary.
# `keywords` is deliberately absent: it is the nämnd's own declared
# classification, published verbatim by the facets, so filtering on one is
# using a value the caller was handed rather than guessing.
FREE_TEXT_FILTER_FIELDS = ("category", "decision_outcome", "entity_names")

_CHUNK_HANDLE_PREFIX = "c"
_DOCUMENT_HANDLE_PREFIX = "d"

# How many distinct values of one facet the vocabulary tool reports per call.
_MAX_VOCABULARY_VALUES = 40


@dataclass
class ChunkRecord:
    document_id: uuid.UUID
    chunk: SearchedChunk


@dataclass
class AnswerSelection:
    """The passages the answer rests on, each with why it was chosen.

    The annotations *are* the selection — a handle cannot be cited without
    saying what it carries, which is what keeps the writing step's guidance
    structured all the way through.
    """

    annotations: list[PassageNote]
    gaps: list[str]

    @property
    def chunk_handles(self) -> list[str]:
        return [note.handle for note in self.annotations]


@dataclass
class ChatState:
    """What the agent has done so far in one run.

    Mutable and single-run: `build_chat_tools` creates one per invocation and
    the executors close over it, so nothing leaks between requests.
    """

    grounded: bool = False
    chunks: dict[str, ChunkRecord] = field(default_factory=dict)
    decisions: dict[str, SearchedDecision] = field(default_factory=dict)
    handle_by_document: dict[uuid.UUID, str] = field(default_factory=dict)
    handle_by_chunk: dict[uuid.UUID, str] = field(default_factory=dict)
    readings: list[DecisionReading] = field(default_factory=list)
    documents_read: set[uuid.UUID] = field(default_factory=set)
    # The last tabular answer. A run that counts more than once keeps the most
    # recent, matching the SQL agent's own "last successful query is the answer".
    tabular: SqlAgentResult | None = None
    selection: AnswerSelection | None = None


def label_for_call(tool: ChatTool, arguments: dict[str, Any]) -> ProgressLabel:
    """Which progress key a call reports under.

    Finer-grained than the tool for search, because "searching" and "narrowing
    to a filtered set" are different enough that a client should be able to say
    which is happening without inspecting the arguments itself.
    """
    match tool:
        case ChatTool.LIST_VOCABULARY:
            return ProgressLabel.VOCABULARY_LIST
        case ChatTool.SEARCH_DECISIONS:
            has_filter = bool(arguments.get("document_filter"))
            return (
                ProgressLabel.SEARCH_FILTERED
                if has_filter
                else ProgressLabel.SEARCH_BROAD
            )
        case ChatTool.READ_DECISION:
            return ProgressLabel.DECISION_READ
        case ChatTool.INSPECT_DECISION:
            return ProgressLabel.DECISION_INSPECT
        case ChatTool.QUERY_CORPUS:
            return ProgressLabel.SQL_QUERY
        case ChatTool.ANSWER:
            return ProgressLabel.ANSWER_COMPOSE


def _ungrounded_fields(document_filter: DocumentFilter) -> list[str]:
    return [
        name for name in FREE_TEXT_FILTER_FIELDS if getattr(document_filter, name, None)
    ]


def _ungrounded_message(fields: list[str]) -> str:
    listed = ", ".join(fields)
    return (
        f"The filter conditions on the free-text field(s) {listed} without their "
        "values having been read. Call list_vocabulary first and build the "
        "filter from values that actually occur — a guessed value matches "
        "nothing and this search does not widen."
    )


def _assign_document_handle(state: ChatState, decision: SearchedDecision) -> str:
    existing = state.handle_by_document.get(decision.document_id)
    if existing is not None:
        state.decisions[existing] = decision
        return existing
    handle = f"{_DOCUMENT_HANDLE_PREFIX}{len(state.handle_by_document) + 1}"
    state.handle_by_document[decision.document_id] = handle
    state.decisions[handle] = decision
    return handle


def _assign_chunk_handle(
    state: ChatState, document_id: uuid.UUID, chunk: SearchedChunk
) -> str:
    existing = state.handle_by_chunk.get(chunk.chunk_id)
    if existing is not None:
        return existing
    handle = f"{_CHUNK_HANDLE_PREFIX}{len(state.handle_by_chunk) + 1}"
    state.handle_by_chunk[chunk.chunk_id] = handle
    state.chunks[handle] = ChunkRecord(document_id=document_id, chunk=chunk)
    return handle


def _chunk_origin(chunk: SearchedChunk) -> str:
    if chunk.section is ChunkSection.APPENDIX:
        return f"{chunk.appendix_label or 'bilaga'} — the appealed decision"
    return "the board's own text"


async def _list_vocabulary(
    toolset: ChatToolset, state: ChatState, *, contains: str | None = None
) -> dict[str, Any]:
    vocabulary = await toolset.vocabulary(contains=contains)
    state.grounded = True

    def values(items: list[Any]) -> list[dict[str, Any]]:
        return [
            {"value": item.value, "count": item.count}
            for item in items[:_MAX_VOCABULARY_VALUES]
        ]

    result: dict[str, Any] = {
        "categories": values(vocabulary.categories),
        "decision_outcomes": values(vocabulary.decision_outcomes),
        "keywords": values(vocabulary.keywords),
        "concepts": values(vocabulary.concepts),
        "document_count": vocabulary.document_count,
        "earliest_decision_date": _as_text(vocabulary.earliest_decision_date),
        "latest_decision_date": _as_text(vocabulary.latest_decision_date),
    }
    if contains is None:
        # The facets do not publish concepts, and an empty list here reads as
        # "the corpus has none" rather than "you have not asked yet".
        result["concepts_note"] = (
            "Concepts are only listed for a `contains` lookup. Call again with "
            "one to see them."
        )
    return result


def _as_text(value: Any) -> str | None:
    return None if value is None else str(value)


async def _search_decisions(
    toolset: ChatToolset,
    state: ChatState,
    settings: ChatAgentSettings,
    *,
    query: str,
    queries: list[str] | None = None,
    document_filter: dict[str, Any] | None = None,
    include_appendices: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    try:
        parsed_filter = DocumentFilter.model_validate(document_filter or {})
    except Exception as exc:
        return {"error": f"The filter could not be read: {exc}"}

    if not state.grounded:
        ungrounded = _ungrounded_fields(parsed_filter)
        if ungrounded:
            return {"error": _ungrounded_message(ungrounded), "refused": True}

    outcome = await toolset.search(
        query=query,
        queries=queries or [],
        document_filter=parsed_filter,
        include_appendices=include_appendices,
        limit=limit or settings.chat_agent_search_limit,
        chunks_per_decision=settings.chat_agent_chunks_per_decision,
    )

    decisions: list[dict[str, Any]] = []
    for decision in outcome.decisions:
        document_handle = _assign_document_handle(state, decision)
        decisions.append(
            {
                "document_id": document_handle,
                "case_number": decision.case_number,
                "decision_date": _as_text(decision.decision_date),
                "decision_outcome": decision.decision_outcome,
                "category": decision.category,
                "summary": decision.summary,
                "chunks": [
                    {
                        "chunk_id": _assign_chunk_handle(
                            state, decision.document_id, chunk
                        ),
                        "text": chunk.text,
                        "origin": _chunk_origin(chunk),
                        "vector_similarity": chunk.vector_similarity,
                    }
                    for chunk in decision.chunks
                ],
            }
        )

    return {
        "decisions": decisions,
        "decision_count": len(decisions),
        "widened_to_appendices": outcome.widened_to_appendices,
        "candidate_document_count": outcome.candidate_document_count,
        "top_vector_similarity": outcome.top_vector_similarity,
    }


def _unknown_handle(handle: str, known: dict[str, Any], kind: str) -> dict[str, Any]:
    available = ", ".join(sorted(known)) or "none yet"
    return {
        "error": (
            f"There is no {kind} {handle!r}. Available: {available}. "
            "Use the handles returned by search_decisions."
        ),
        "refused": True,
    }


async def _read_decision(
    toolset: ChatToolset,
    state: ChatState,
    settings: ChatAgentSettings,
    reader_provider: LLMProvider | None,
    *,
    document_id: str,
    question: str,
    include_appendices: bool = False,
) -> dict[str, Any]:
    decision = state.decisions.get(document_id)
    if decision is None:
        return _unknown_handle(document_id, state.decisions, "decision")

    if (
        decision.document_id not in state.documents_read
        and len(state.documents_read) >= settings.chat_agent_max_documents_read
    ):
        return {
            "error": (
                f"The reading budget for this run is spent "
                f"({settings.chat_agent_max_documents_read} decisions). Answer "
                "from the passages you already have."
            ),
            "refused": True,
        }

    text: DecisionText | None = await toolset.decision_text(
        document_id=decision.document_id, include_appendices=include_appendices
    )
    if text is None or not text.chunks:
        return {"error": f"Decision {document_id} has no readable text."}

    try:
        selection = await read_decision_text(
            text,
            question,
            max_selected=settings.chat_agent_max_chunks_per_reading,
            summary_words=settings.chat_agent_reading_summary_words,
            provider=reader_provider,
        )
    except Exception:
        # A reader that returns output the schema cannot read is a refusal, not
        # a failed turn: every other expected failure here comes back as a tool
        # result, and the orchestrator repairs through the loop's ordinary path.
        logger.exception("Reading %s returned unreadable output", document_id)
        return {
            "error": (
                f"Decision {document_id} could not be read this time. Answer "
                "from the passages you already have, or try another decision."
            ),
            "refused": True,
        }

    # Counted as read whatever the verdict: the call was made and paid for, and
    # a budget that only counted useful readings would let a run of dead ends
    # spend without bound.
    state.documents_read.add(decision.document_id)

    if selection.relevance == "nothing":
        # Nothing is recorded, so nothing reaches the writing step. A decision
        # that does not address the question used to arrive there as a paragraph
        # of prose saying so, which the writer then had to read and discard.
        return {
            "document_id": document_id,
            "relevance": "nothing",
            "note": "This decision has nothing to say about the question.",
        }

    handles, unknown = _handles_for_reading(state, decision, text, selection, settings)
    if unknown:
        logger.info(
            "Reading %s pointed at passages outside the decision: %s",
            document_id,
            unknown,
        )
    if not handles:
        return {
            "document_id": document_id,
            "relevance": selection.relevance,
            "note": "The reading pointed at no passage of this decision.",
        }

    state.readings.append(
        DecisionReading(
            case_number=text.case_number or document_id,
            handles=list(handles),
            summary=selection.summary,
        )
    )
    return {
        "document_id": document_id,
        "relevance": selection.relevance,
        "summary": selection.summary,
        "passages": [
            {
                "chunk_id": handle,
                "text": state.chunks[handle].chunk.text,
                "origin": _chunk_origin(state.chunks[handle].chunk),
            }
            for handle in handles
        ],
    }


def _handles_for_reading(
    state: ChatState,
    decision: SearchedDecision,
    text: DecisionText,
    selection: ReadingSelection,
    settings: ChatAgentSettings,
) -> tuple[list[str], list[int]]:
    """The reading's chosen passages, as citable handles.

    The index addresses `text.chunks` by position, which is what the reader was
    shown. Each survivor goes through `_assign_chunk_handle`, so a passage search
    already surfaced comes back under the handle it already has rather than a
    second one pointing at the same text.
    """
    handles: list[str] = []
    unknown: list[int] = []
    seen: set[int] = set()

    for index in selection.chunk_indices:
        if not 0 <= index < len(text.chunks):
            unknown.append(index)
            continue
        if index in seen:
            continue
        seen.add(index)
        if len(handles) >= settings.chat_agent_max_chunks_per_reading:
            continue
        chunk = text.chunks[index]
        handles.append(
            _assign_chunk_handle(
                state,
                decision.document_id,
                SearchedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    section=chunk.section,
                    appendix_label=chunk.appendix_label,
                ),
            )
        )

    return handles, unknown


async def _inspect_decision(
    toolset: ChatToolset, state: ChatState, *, document_id: str
) -> dict[str, Any]:
    decision = state.decisions.get(document_id)
    if decision is None:
        return _unknown_handle(document_id, state.decisions, "decision")

    profile = await toolset.decision_profile(document_id=decision.document_id)
    if profile is None:
        return {"error": f"Decision {document_id} could not be inspected."}

    return {
        "document_id": document_id,
        "case_number": profile.case_number,
        "decision_date": _as_text(profile.decision_date),
        "decision_outcome": profile.decision_outcome,
        "category": profile.category,
        "headline": profile.headline,
        "summary": profile.summary,
        "keywords": profile.keywords,
        "concepts": profile.concepts,
        "regulations": profile.regulations,
        "roles": profile.roles,
        "parishes": profile.parishes,
        "cites": profile.references_out,
        "cited_by": profile.references_in,
    }


async def _query_corpus(
    toolset: ChatToolset, state: ChatState, *, question: str
) -> dict[str, Any]:
    result = await toolset.tabular_query(question=question)
    state.tabular = result
    if not result.answered:
        return {"answered": False, "note": result.note}
    return {
        "answered": True,
        "sql": result.sql,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "assumptions": result.assumptions,
    }


async def _answer(
    state: ChatState,
    settings: ChatAgentSettings,
    *,
    annotations: list[dict[str, Any]] | None = None,
    gaps: list[str] | None = None,
) -> dict[str, Any]:
    known: list[PassageNote] = []
    unknown: list[str] = []

    for raw in annotations or []:
        try:
            note = PassageNote.model_validate(raw)
        except Exception:
            # A malformed annotation is a dropped passage, not a failed turn:
            # the rest of the selection is still good evidence.
            logger.info("Chat agent sent an unreadable annotation: %r", raw)
            continue
        if note.handle in state.chunks:
            known.append(note)
        else:
            unknown.append(note.handle)

    state.selection = AnswerSelection(
        annotations=known[: settings.chat_agent_max_chunks_cited],
        gaps=list(gaps or []),
    )
    if unknown:
        logger.info("Chat agent selected unknown chunk handles: %s", unknown)
    return {
        "ok": True,
        "cited_chunks": len(state.selection.annotations),
        "ignored_unknown_handles": unknown,
    }


_TOOL_DEFINITIONS = [
    ToolDefinition(
        name=ChatTool.LIST_VOCABULARY,
        description=(
            "Lists the category, outcome and keyword values that actually "
            "occur in the corpus, with a count for each. Call this before "
            "filtering on category, decision_outcome or entity_names — "
            "search_decisions refuses such a filter otherwise. Legal concepts "
            "are returned only for a `contains` lookup."
        ),
        parameters={
            "type": "object",
            "properties": {
                "contains": {
                    "type": "string",
                    "description": (
                        "Optional. Only values containing this text. Use it to "
                        "reach keywords and concepts beyond the most common."
                    ),
                }
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name=ChatTool.SEARCH_DECISIONS,
        description=(
            "Searches the decisions semantically and lexically at once and "
            "returns the matching passages grouped by decision. Each passage "
            "carries a handle (c1, c2, ...) to cite it by, and each decision a "
            "handle (d1, d2, ...) to read or inspect it by."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The question, in Swedish.",
                },
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional alternative phrasings, searched alongside "
                        "the query and fused with it."
                    ),
                },
                "document_filter": {
                    "type": "object",
                    "description": (
                        "Optional. Fields: date_from, date_to (YYYY-MM-DD), "
                        "category, decision_outcome, case_number, "
                        "decision_number, entity_names, entity_types, "
                        "keywords, references_case_number."
                    ),
                },
                "include_appendices": {
                    "type": "boolean",
                    "description": (
                        "Search the appealed decisions too. False by default — "
                        "set it only when the question is about what the lower "
                        "instance decided."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional. Decisions to return.",
                },
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name=ChatTool.READ_DECISION,
        description=(
            "Hands one whole decision to a reader together with your question, "
            "and returns what it found. Use it when the passages leave the "
            "question open — not as a matter of course."
        ),
        parameters={
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "A decision handle from search_decisions, e.g. d2.",
                },
                "question": {
                    "type": "string",
                    "description": (
                        "What the reader should look for, in Swedish. Be "
                        "specific — this is all it is told."
                    ),
                },
                "include_appendices": {
                    "type": "boolean",
                    "description": "Include the appealed decision. False by default.",
                },
            },
            "required": ["document_id", "question"],
        },
    ),
    ToolDefinition(
        name=ChatTool.INSPECT_DECISION,
        description=(
            "One decision's keywords, legal concepts, regulations, roles, "
            "parishes and citation graph in both directions. Metadata only — "
            "use read_decision for the text."
        ),
        parameters={
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "A decision handle from search_decisions, e.g. d2.",
                }
            },
            "required": ["document_id"],
        },
    ),
    ToolDefinition(
        name=ChatTool.QUERY_CORPUS,
        description=(
            "Answers counting, grouping and aggregation questions with SQL over "
            "the whole corpus. Use it for any 'how many', 'which year' or 'most "
            "common' question — search results are a ranked sample and counting "
            "them gives the wrong number."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The counting question, in Swedish.",
                }
            },
            "required": ["question"],
        },
    ),
    ToolDefinition(
        name=ChatTool.ANSWER,
        description=(
            "Ends your turn. Name each passage that carries the answer and say "
            "what it carries. Call this exactly once, when you have enough."
        ),
        parameters={
            "type": "object",
            "properties": {
                "annotations": {
                    "type": "array",
                    "description": (
                        "One entry per passage the answer rests on. These are "
                        "quoted verbatim by the writing step, so choose few and "
                        "choose well."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "handle": {
                                "type": "string",
                                "description": (
                                    "A passage handle from search_decisions, e.g. c1."
                                ),
                            },
                            "carries": {
                                "type": "string",
                                "description": (
                                    "What this passage establishes, in Swedish. "
                                    "A pointer for the writer — never the "
                                    "finding itself, which it reads for itself."
                                ),
                            },
                            "caution": {
                                "type": "string",
                                "description": (
                                    "What the writer must watch for, e.g. "
                                    "'bilaga, underinstansens ord'. Omit when "
                                    "there is nothing to flag."
                                ),
                            },
                        },
                        "required": ["handle", "carries"],
                    },
                },
                "gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "What the evidence does not support, in Swedish. One "
                        "short sentence each. Empty when it covers the question."
                    ),
                },
            },
            "required": ["annotations"],
        },
    ),
]


def build_chat_tools(
    toolset: ChatToolset,
    settings: ChatAgentSettings,
    *,
    reader_provider: LLMProvider | None = None,
) -> tuple[list[ToolDefinition], dict[str, Any], ChatState]:
    """Tool definitions, their executors, and the state all of them share.

    The state is returned rather than hidden so the caller can read the
    selected evidence back out once the loop has finished.
    """
    state = ChatState()

    async def list_vocabulary(contains: str | None = None) -> dict[str, Any]:
        return await _list_vocabulary(toolset, state, contains=contains)

    async def search_decisions(
        query: str,
        queries: list[str] | None = None,
        document_filter: dict[str, Any] | None = None,
        include_appendices: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await _search_decisions(
            toolset,
            state,
            settings,
            query=query,
            queries=queries,
            document_filter=document_filter,
            include_appendices=include_appendices,
            limit=limit,
        )

    async def read_decision(
        document_id: str, question: str, include_appendices: bool = False
    ) -> dict[str, Any]:
        return await _read_decision(
            toolset,
            state,
            settings,
            reader_provider,
            document_id=document_id,
            question=question,
            include_appendices=include_appendices,
        )

    async def inspect_decision(document_id: str) -> dict[str, Any]:
        return await _inspect_decision(toolset, state, document_id=document_id)

    async def query_corpus(question: str) -> dict[str, Any]:
        return await _query_corpus(toolset, state, question=question)

    async def answer(
        annotations: list[dict[str, Any]] | None = None,
        gaps: list[str] | None = None,
    ) -> dict[str, Any]:
        return await _answer(state, settings, annotations=annotations, gaps=gaps)

    executors = {
        ChatTool.LIST_VOCABULARY: list_vocabulary,
        ChatTool.SEARCH_DECISIONS: search_decisions,
        ChatTool.READ_DECISION: read_decision,
        ChatTool.INSPECT_DECISION: inspect_decision,
        ChatTool.QUERY_CORPUS: query_corpus,
        ChatTool.ANSWER: answer,
    }
    return _TOOL_DEFINITIONS, executors, state
