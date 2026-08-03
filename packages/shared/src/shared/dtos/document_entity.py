import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

# `relevance` is stored as ``str``; its values come from
# ``shared.enums.EntityRelevance``, which the extraction logic uses. See the note in
# ``shared/dtos/task.py`` for the rationale.


class DocumentEntityCreate(BaseModel):
    document_id: uuid.UUID
    entity_id: uuid.UUID
    relevance: str


class DocumentEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    entity_id: uuid.UUID
    relevance: str


class DocumentEntityDetail(BaseModel):
    """One edge with the entity resolved — what a reader of a document needs.

    ``DocumentEntityRead`` carries bare ids, so rendering a document's concepts
    from it would cost a lookup per edge.
    """

    entity_id: uuid.UUID
    name: str
    type: str
    relevance: str


class EntityDocumentRef(BaseModel):
    """One edge with the document resolved — the reverse traversal hop."""

    document_id: uuid.UUID
    case_number: str | None
    decision_number: str | None
    decision_date: date | None
    headline: str | None
    category: str | None
    decision_outcome: str | None
    relevance: str
