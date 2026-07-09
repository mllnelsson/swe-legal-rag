from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document_entity import DocumentEntityCreate
from shared.dtos.entity import EntityCreate
from shared.repositories import DocumentEntityRepo, EntityRepo
from worker_extract.models import ExtractedEntity, Relevance


def normalize_entity_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def _deduplicate_entities(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
    seen: dict[tuple[str, str], ExtractedEntity] = {}
    for entity in entities:
        key = (normalize_entity_name(entity.name), str(entity.type))
        if key not in seen or entity.relevance == Relevance.PRIMARY:
            seen[key] = entity
    return list(seen.values())


async def persist_entities(
    session: AsyncSession,
    entity_repo: EntityRepo,
    doc_entity_repo: DocumentEntityRepo,
    document_id: UUID,
    entities: list[ExtractedEntity],
) -> None:
    deduped = _deduplicate_entities(entities)
    for entity in deduped:
        normalized_name = normalize_entity_name(entity.name)
        entity_read = await entity_repo.upsert(
            session, EntityCreate(name=normalized_name, type=str(entity.type))
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=document_id,
                entity_id=entity_read.id,
                relevance=str(entity.relevance),
            ),
        )
