from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from _fsstore import store_of
from shared.dtos.document_entity import DocumentEntityCreate, DocumentEntityRead

_PRIMARY = "primary"


def _rows(session: AsyncSession) -> list[DocumentEntityRead]:
    return store_of(session).rows["document_entities"]


async def upsert(
    session: AsyncSession, dto: DocumentEntityCreate
) -> DocumentEntityRead:
    rows = _rows(session)
    for i, de in enumerate(rows):
        if de.document_id == dto.document_id and de.entity_id == dto.entity_id:
            if dto.relevance == _PRIMARY and de.relevance != _PRIMARY:
                rows[i] = de.model_copy(update={"relevance": _PRIMARY})
            return rows[i]
    de = DocumentEntityRead(
        document_id=dto.document_id, entity_id=dto.entity_id, relevance=dto.relevance
    )
    rows.append(de)
    return de
