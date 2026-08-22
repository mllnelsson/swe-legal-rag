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
    """One passage as the writing step sees it.

    Only what the prompt actually renders. A date, an outcome and a fused score
    used to travel here and reach no template — the writer quotes the passage
    and attributes it, and grades nothing.
    """

    model_config = ConfigDict(frozen=True)

    chunk_text: str
    case_number: str
    # The orchestrator's handle for this passage, e.g. "c3". The writer marks
    # each claim with it, which is what makes a sentence traceable to a source.
    handle: str
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None


class PassageNote(BaseModel):
    """The orchestrator's guidance about one passage.

    Guidance, never a source: the writer verifies everything in the passage
    text itself. Structured so that a claim has nowhere to hide.
    """

    model_config = ConfigDict(frozen=True)

    handle: str
    carries: str
    caution: str | None = None


class DecisionReading(BaseModel):
    """What a reading sub-agent found in one whole decision.

    Handles, never text. A full decision runs to ~10k characters on average and
    165k at worst; the point of reading it in a sub-agent is that only this
    comes back — and the passages it names are carried by `SynthesizeRequest.chunks`
    like any other, so the writing step reads them verbatim rather than reading
    a model's account of them.

    `summary` is guidance about how those passages connect, with exactly the
    status of `PassageNote.carries`: it says where a finding lives, never what
    the finding is.
    """

    model_config = ConfigDict(frozen=True)

    case_number: str
    handles: list[str] = []
    summary: str = ""


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
    # The agent's handoff: why each passage was chosen, and what the evidence
    # does not reach. Guidance for the writer, never something it may assert.
    annotations: list[PassageNote] = []
    gaps: list[str] = []


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
