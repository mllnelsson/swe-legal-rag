from __future__ import annotations

import json
import logging

from worker_extract.models import (
    EntityType,
    ExtractionResult,
    ExtractedEntity,
    ExtractedReference,
    Relevance,
)

logger = logging.getLogger(__name__)

_VALID_TYPES = {e.value for e in EntityType}
_VALID_RELEVANCES = {r.value for r in Relevance}


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _deduplicate_entities(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
    seen: dict[tuple[str, str], ExtractedEntity] = {}
    for entity in entities:
        key = (entity.name, str(entity.type))
        if key not in seen or entity.relevance == Relevance.PRIMARY:
            seen[key] = entity
    return list(seen.values())


def _deduplicate_references(
    references: list[ExtractedReference],
) -> list[ExtractedReference]:
    seen: dict[str, ExtractedReference] = {}
    for ref in references:
        if ref.case_number not in seen:
            seen[ref.case_number] = ref
    return list(seen.values())


def parse_llm_response(raw_json: str) -> ExtractionResult:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse LLM response as JSON: %s", exc)
        raise

    raw_entities = data.get("entities", [])
    raw_references = data.get("references", [])

    entities: list[ExtractedEntity] = []
    for item in raw_entities:
        entity_type = item.get("type", "")
        relevance = item.get("relevance", "")
        if entity_type not in _VALID_TYPES:
            logger.warning("Skipping entity with invalid type: %r", entity_type)
            continue
        if relevance not in _VALID_RELEVANCES:
            logger.warning("Skipping entity with invalid relevance: %r", relevance)
            continue
        name = _normalize_name(item.get("name", ""))
        if not name:
            continue
        entities.append(
            ExtractedEntity(
                name=name,
                type=EntityType(entity_type),
                relevance=Relevance(relevance),
            )
        )

    references: list[ExtractedReference] = []
    for item in raw_references:
        case_number = item.get("case_number", "").strip()
        reference_context = item.get("reference_context", "").strip()
        if not case_number:
            continue
        references.append(
            ExtractedReference(
                case_number=case_number, reference_context=reference_context
            )
        )

    return ExtractionResult(
        entities=_deduplicate_entities(entities),
        references=_deduplicate_references(references),
    )
