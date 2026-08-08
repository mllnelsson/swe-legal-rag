from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from _fsstore import store_of
from shared.dtos.document_entity import DocumentEntityCreate, DocumentEntityRead
from shared.enums import EntityRelevance


def _rows(session: AsyncSession) -> list[DocumentEntityRead]:
    return store_of(session).rows["document_entities"]


async def upsert(
    session: AsyncSession, dto: DocumentEntityCreate
) -> DocumentEntityRead:
    rows = _rows(session)
    for i, de in enumerate(rows):
        if de.document_id == dto.document_id and de.entity_id == dto.entity_id:
            if dto.relevance == EntityRelevance.PRIMARY and (
                de.relevance != EntityRelevance.PRIMARY
            ):
                rows[i] = de.model_copy(update={"relevance": EntityRelevance.PRIMARY})
            return rows[i]
    de = DocumentEntityRead(
        document_id=dto.document_id, entity_id=dto.entity_id, relevance=dto.relevance
    )
    rows.append(de)
    return de


async def delete_missing_for_document(
    session: AsyncSession, document_id: uuid.UUID, entity_ids: set[uuid.UUID]
) -> None:
    rows = _rows(session)
    rows[:] = [
        de for de in rows if de.document_id != document_id or de.entity_id in entity_ids
    ]
