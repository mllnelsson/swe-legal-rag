import uuid

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
