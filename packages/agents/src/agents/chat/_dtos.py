"""The conversational agent's wire contract, as plain data.

Deliberately free of FastAPI types, the same way `sql/_dtos.py` is, so the same
models serve an HTTP route, a test, or a batch runner. Deliberately free of
`api` types too: the toolset shapes below are what keeps the dependency running
`api -> agents` and never the other way.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from shared.enums import ChunkSection

from agents.sql._dtos import SqlAttempt

MAX_CHAT_QUESTION_CHARS = 4000

# How much of a cited passage travels on the sources event. The passage itself
# reached the model in full; this is a label for the reader, not evidence.
EXCERPT_MAX_CHARS = 200


class ChatTool(StrEnum):
    """The tools the orchestrator is given.

    The values are the names the model calls, so they are also what a trace
    record and a progress event carry.
    """

    LIST_VOCABULARY = "list_vocabulary"
    SEARCH_DECISIONS = "search_decisions"
    READ_DECISION = "read_decision"
    INSPECT_DECISION = "inspect_decision"
    QUERY_CORPUS = "query_corpus"
    ANSWER = "answer"


class PassageNote(BaseModel):
    """What the orchestrator has to say about one passage it selected.

    Structured rather than prose, and that is the whole point. The writing step
    is forbidden from treating guidance as a source, but freeform notes have no
    enforceable line between "c3 carries the deadline rule" (guidance, wanted)
    and "the deadline is three weeks" (a claim, forbidden). These fields have
    nowhere to put the second, so the rule is a shape rather than a request.
    """

    model_config = ConfigDict(frozen=True)

    handle: str
    # What this passage establishes, in Swedish. A pointer, never the finding.
    carries: str
    # What the writer must watch for — "bilaga, underinstansens ord", "obiter",
    # "gäller bara församlingar". None when there is nothing to flag.
    caution: str | None = None


class ProgressLabel(StrEnum):
    """What a client may say is happening, as a key rather than a sentence.

    The API owns this vocabulary; the client owns the words. Keeping the
    user-facing string out of here means no translation lives in the backend and
    no client has to parse tool arguments to decide what to show.

    Finer-grained than `ChatTool` on purpose: one tool can report more than one
    kind of step without a client inspecting `detail`.
    """

    VOCABULARY_LIST = "vocabulary.list"
    SEARCH_BROAD = "search.broad"
    SEARCH_FILTERED = "search.filtered"
    SEARCH_REFUSED = "search.refused"
    SQL_QUERY = "sql.query"
    DECISION_READ = "decision.read"
    DECISION_INSPECT = "decision.inspect"
    ANSWER_COMPOSE = "answer.compose"


class ToolStatus(StrEnum):
    OK = "ok"
    # The tool declined on policy — an ungrounded filter, a budget reached. Not
    # a failure: the loop repairs itself from it.
    REFUSED = "refused"
    ERROR = "error"


class ChatAgentRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, max_length=MAX_CHAT_QUESTION_CHARS)
    # Prior turns, oldest first, as `{"role": ..., "content": ...}` — the shape
    # `session_service.history_for_llm` already returns.
    history: list[dict] = []


# --- what the toolset hands back -------------------------------------------


class VocabularyValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str
    count: int


class Vocabulary(BaseModel):
    """The values a filter will actually match.

    `categories` and `decision_outcomes` are free text lifted off the PDFs, so
    they cannot be guessed — reading them is a precondition for filtering on
    them, not a courtesy.
    """

    model_config = ConfigDict(frozen=True)

    categories: list[VocabularyValue] = []
    decision_outcomes: list[VocabularyValue] = []
    keywords: list[VocabularyValue] = []
    concepts: list[VocabularyValue] = []
    document_count: int = 0
    earliest_decision_date: date | None = None
    latest_decision_date: date | None = None


class SearchedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: uuid.UUID
    text: str
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None
    # Cosine similarity, comparable across queries — how the agent tells a close
    # match from the merely nearest paragraph. None when only the lexical arm
    # returned this chunk.
    vector_similarity: float | None = None


class SearchedDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: uuid.UUID
    case_number: str | None = None
    decision_date: date | None = None
    decision_outcome: str | None = None
    category: str | None = None
    summary: str | None = None
    chunks: list[SearchedChunk] = []


class SearchOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    decisions: list[SearchedDecision] = []
    total: int = 0
    # Mirrors the search diagnostics the deterministic path already publishes, so
    # the agent can tell "the corpus does not address this" from "the filter
    # excluded everything".
    widened_to_appendices: bool = False
    candidate_document_count: int | None = None
    top_vector_similarity: float | None = None


class DecisionTextChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_index: int
    text: str
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None


class DecisionText(BaseModel):
    """One decision's text in reading order.

    Chunks rather than `documents.raw_text`: raw_text is the flattened PDF, with
    the board's ruling and the decision it was appealed from concatenated and no
    marker between them. Every honesty rule downstream depends on telling those
    apart, so the section travels with the text.
    """

    model_config = ConfigDict(frozen=True)

    document_id: uuid.UUID
    case_number: str | None = None
    chunks: list[DecisionTextChunk] = []


class DecisionProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: uuid.UUID
    case_number: str | None = None
    decision_date: date | None = None
    decision_outcome: str | None = None
    category: str | None = None
    headline: str | None = None
    summary: str | None = None
    keywords: list[str] = []
    concepts: list[str] = []
    regulations: list[str] = []
    roles: list[str] = []
    parishes: list[str] = []
    # Case numbers, both directions of the citation graph.
    references_out: list[str] = []
    references_in: list[str] = []


# --- what the agent emits ---------------------------------------------------


class SourceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: uuid.UUID
    case_number: str | None = None
    decision_date: date | None = None
    decision_outcome: str | None = None
    category: str | None = None
    excerpt: str = ""
    # "appendix" means the appealed decision — the lower instance's own words,
    # which the board may have overturned. A client must not present such an
    # excerpt as the board's reasoning.
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None


class ToolCallEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["tool_call"] = "tool_call"
    id: str
    tool: ChatTool
    label: ProgressLabel
    # Structured, never prose. Optional for a client — it exists so a later
    # frontend can enrich a label without a contract change.
    detail: dict = {}


class ToolResultEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["tool_result"] = "tool_result"
    id: str
    tool: ChatTool
    label: ProgressLabel
    status: ToolStatus = ToolStatus.OK
    detail: dict = {}


class SqlEvent(BaseModel):
    """The query behind a count, surfaced before the answer asserts the number.

    Not decorative and not optional: a count reads as authoritative and carries
    no excerpt to check it against, so the caller's obligation is to show the
    query it came from.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["sql"] = "sql"
    answered: bool
    sql: str | None = None
    columns: list[str] = []
    rows: list[list[str | int | float | bool | None]] = []
    row_count: int = 0
    truncated: bool = False
    assumptions: list[str] = []
    attempts: list[SqlAttempt] = []


class TokenEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["token"] = "token"
    text: str


class SourcesEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["sources"] = "sources"
    sources: list[SourceReference] = []


class DoneEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["done"] = "done"


class ErrorEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["error"] = "error"
    message: str


AgentEvent = (
    ToolCallEvent
    | ToolResultEvent
    | SqlEvent
    | TokenEvent
    | SourcesEvent
    | DoneEvent
    | ErrorEvent
)
