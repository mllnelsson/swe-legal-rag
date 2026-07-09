from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# The entity vocabularies live in shared.enums (single source of truth used by the
# DTOs too); re-exported here so worker-extract code has one import point for its
# extraction models and their field types.
from shared.enums import EntityRelevance, EntityType

__all__ = [
    "EntityType",
    "EntityRelevance",
    "ExtractedEntity",
    "ExtractedReference",
    "ExtractionResult",
]


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type: EntityType
    relevance: EntityRelevance


class ExtractedReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_number: str
    reference_context: str


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    entities: list[ExtractedEntity]
    references: list[ExtractedReference]
