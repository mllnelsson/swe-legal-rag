from __future__ import annotations

from ai import extract_entities as ai_extract_entities
from ai.dtos import EntityResult

from worker_extract.models import (
    EntityType,
    ExtractionResult,
    ExtractedEntity,
    ExtractedReference,
    Relevance,
)

_VALID_TYPES = {e.value for e in EntityType}
_VALID_RELEVANCES = {r.value for r in Relevance}


def _map_entity_result(result: EntityResult) -> ExtractionResult:
    entities = [
        ExtractedEntity(
            name=e.name, type=EntityType(e.type), relevance=Relevance(e.relevance)
        )
        for e in result.entities
        if e.type in _VALID_TYPES and e.relevance in _VALID_RELEVANCES
    ]
    references = [
        ExtractedReference(
            case_number=r.case_number, reference_context=r.reference_context
        )
        for r in result.references
    ]
    return ExtractionResult(entities=entities, references=references)


class LLMStrategy:
    async def extract(
        self, document_text: str, case_number: str | None = None
    ) -> ExtractionResult:
        result = await ai_extract_entities(document_text, case_number)
        return _map_entity_result(result)
