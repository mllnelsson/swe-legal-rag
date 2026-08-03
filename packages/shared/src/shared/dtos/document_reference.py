import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class DocumentReferenceCreate(BaseModel):
    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    reference_context: str | None = None


class DocumentReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    reference_context: str | None


class ReferenceEdge(BaseModel):
    """A citation with the *other* document resolved, ready to render as a link.

    Which document ``document_id`` names depends on which side of
    ``ReferenceEdges`` the edge sits on.
    """

    document_id: uuid.UUID
    case_number: str | None
    decision_number: str | None
    decision_date: date | None
    headline: str | None
    reference_context: str | None


class ReferenceEdges(BaseModel):
    """Both directions of a document's citation graph, one hop out."""

    outgoing: list[ReferenceEdge]
    incoming: list[ReferenceEdge]
