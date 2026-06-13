from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


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


class ChunkContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_text: str
    case_number: str
    decision_date: str | None = None
    decision_outcome: str | None = None
    score: float


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    chunks: list[ChunkContext]
    conversation_history: list[dict] = []


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
    type: str
    relevance: str


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
