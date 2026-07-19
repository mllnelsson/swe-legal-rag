"""Shared entity-normalization and de-duplication helpers.

Both the LLM-response parser (`parsing.py`), the persistence service
(`services/entity_service.py`), and the fallback strategy merge
(`extractors/factory.py`) need to collapse entities that refer to the same
thing. Keeping one implementation here avoids the three copies drifting apart.
"""

from __future__ import annotations

import re

from worker_extract.models import ExtractedEntity, EntityRelevance

__all__ = ["normalize_entity_name", "deduplicate_entities"]


def normalize_entity_name(name: str) -> str:
    """Collapse internal whitespace and lowercase, giving entities a stable
    identity regardless of incidental spacing or casing."""
    return re.sub(r"\s+", " ", name.strip()).lower()


def deduplicate_entities(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
    """Collapse entities sharing a (normalized name, type) key. When the same
    entity appears with different relevances, the PRIMARY one wins."""
    seen: dict[tuple[str, str], ExtractedEntity] = {}
    for entity in entities:
        key = (normalize_entity_name(entity.name), str(entity.type))
        if key not in seen or entity.relevance == EntityRelevance.PRIMARY:
            seen[key] = entity
    return list(seen.values())
