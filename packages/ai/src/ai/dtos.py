from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from shared.enums import ChunkSection, EntityRelevance, EntityType


class DateFilter(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: date | None = None
    end: date | None = None


class DecomposeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    conversation_history: list[dict] = []


class DecomposeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    filters: DateFilter | None = None
    categories: list[str]
    entity_refs: list[str]
    semantic_query: str
    # True when the question is about the decision under appeal rather than
    # Överklagandenämndens own ruling — see the query-decomposition prompt.
    include_appendices: bool = False


class QueryExpansionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    max_variants: int


class QueryExpansionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Alternative phrasings only — deliberately no filters and no rewritten
    # "best" query. Expansion adds rankings to the fusion; it never replaces the
    # question the caller asked, so it cannot lose a hit the original found.
    variants: list[str]


class ChunkContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_text: str
    case_number: str
    decision_date: str | None = None
    decision_outcome: str | None = None
    score: float
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None


class DecisionReading(BaseModel):
    """What a reading sub-agent got out of one whole decision.

    The extract, never the decision. A full decision runs to ~10k characters on
    average and 165k at worst; the point of reading it in a sub-agent is that
    only this comes back.
    """

    model_config = ConfigDict(frozen=True)

    case_number: str
    extract: str


class TabularEvidence(BaseModel):
    """A counting or aggregating answer, with the query that produced it.

    `sql` travels with the rows because a count reads as authoritative and
    carries no excerpt to check it against — the obligation the SQL agent places
    on every caller.
    """

    model_config = ConfigDict(frozen=True)

    sql: str
    columns: list[str]
    rows: list[list[str | int | float | bool | None]]
    row_count: int
    truncated: bool = False
    assumptions: list[str] = []


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    chunks: list[ChunkContext]
    conversation_history: list[dict] = []
    # The rest of the evidence an agent gathered. Empty on the passage-only
    # path, which is what the deterministic search surface produces.
    readings: list[DecisionReading] = []
    tabular: TabularEvidence | None = None
    # The agent's own terse handoff — why these passages, what to be careful of.
    notes: str = ""


class SourceCitation(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_number: str
    decision_date: str | None = None
    outcome: str | None = None
    excerpt: str
    pdf_url: str | None = None


class MetadataRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_text: str


class MetadataResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_number: str | None = None
    decision_date: str | None = None
    decision_outcome: str | None = None
    category: str | None = None


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type: EntityType
    relevance: EntityRelevance


class ExtractedReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_number: str
    reference_context: str


class EntityRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_text: str
    case_number: str | None = None


class EntityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    entities: list[ExtractedEntity]
    references: list[ExtractedReference]


class SummarizeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_text: str


class SummarizeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str


class EmbedRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    texts: list[str]


class EmbedResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    embeddings: list[list[float]]
