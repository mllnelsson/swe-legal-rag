from __future__ import annotations

from enum import StrEnum, auto

from pydantic import BaseModel, ConfigDict


class EntityType(StrEnum):
    LEGAL_CONCEPT = auto()
    ROLE = auto()
    PARISH = auto()
    REGULATION = auto()


class Relevance(StrEnum):
    PRIMARY = auto()
    MENTIONED = auto()


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type: EntityType
    relevance: Relevance


class ExtractedReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_number: str
    reference_context: str


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    entities: list[ExtractedEntity]
    references: list[ExtractedReference]
