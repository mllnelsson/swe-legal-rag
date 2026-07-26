import uuid
from datetime import date

from pydantic import BaseModel

from shared.enums import ChunkSection


class DocumentFilter(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    category: str | None = None
    decision_outcome: str | None = None
    entity_names: list[str] = []
    entity_types: list[str] = []
    references_case_number: str | None = None


class ChunkSearchResult(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_text: str
    chunk_index: int
    score: float
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None
