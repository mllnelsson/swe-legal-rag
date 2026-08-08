from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document_entity import DocumentEntityCreate
from shared.dtos.entity import EntityCreate
from shared.repositories import DocumentEntityRepo, EntityRepo
from worker_extract.entities import deduplicate_entities, normalize_entity_name
from ai.dtos import ExtractedEntity


async def persist_entities(
    session: AsyncSession,
    entity_repo: EntityRepo,
    doc_entity_repo: DocumentEntityRepo,
    document_id: UUID,
    entities: list[ExtractedEntity],
) -> None:
    deduped = deduplicate_entities(entities)
    written: set[UUID] = set()
    for entity in deduped:
        normalized_name = normalize_entity_name(entity.name)
        entity_read = await entity_repo.upsert(
            session, EntityCreate(name=normalized_name, type=entity.type)
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=document_id,
                entity_id=entity_read.id,
                relevance=entity.relevance,
            ),
        )
        written.add(entity_read.id)

    # This document's entity set is whatever this run found — not that union'd with
    # whatever every previous run found. Without the delete, re-extracting after a
    # rule change adds the corrected entities and keeps the superseded ones beside
    # them, which is indistinguishable from the fix not having worked.
    await doc_entity_repo.delete_missing_for_document(session, document_id, written)
