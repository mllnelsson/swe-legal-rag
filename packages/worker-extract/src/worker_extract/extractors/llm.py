from __future__ import annotations

from ai import extract_entities as ai_extract_entities
from ai.dtos import EntityResult
from llm_core import LLMProvider
from shared.segmentation import DocumentSegments

from worker_extract.models import (
    ExtractionResult,
    ExtractedEntity,
    ExtractedReference,
)


def _map_entity_result(result: EntityResult) -> ExtractionResult:
    # ai.dtos already types type/relevance as the shared enums, so the LLM's
    # structured output is validated to the vocabulary at parse time — no extra
    # filtering or coercion is needed here.
    entities = [
        ExtractedEntity(name=e.name, type=e.type, relevance=e.relevance)
        for e in result.entities
    ]
    references = [
        ExtractedReference(
            case_number=r.case_number, reference_context=r.reference_context
        )
        for r in result.references
    ]
    return ExtractionResult(entities=entities, references=references)


class LLMStrategy:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    async def extract(
        self, segments: DocumentSegments, case_number: str | None = None
    ) -> ExtractionResult:
        # Body only. The appendix is the appealed decision written in the same
        # register, and the model has no way to tell whose reasoning is whose once
        # the two are concatenated.
        result = await ai_extract_entities(
            segments.body, case_number, provider=self._provider
        )
        return _map_entity_result(result)
