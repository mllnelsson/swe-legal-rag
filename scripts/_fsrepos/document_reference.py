from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from _fsstore import store_of
from shared.dtos.document_reference import (
    DocumentReferenceCreate,
    DocumentReferenceRead,
)


def _rows(session: AsyncSession) -> list[DocumentReferenceRead]:
    return store_of(session).rows["references"]


async def upsert(
    session: AsyncSession, dto: DocumentReferenceCreate
) -> DocumentReferenceRead:
    rows = _rows(session)
    existing = next(
        (
            r
            for r in rows
            if r.source_document_id == dto.source_document_id
            and r.target_document_id == dto.target_document_id
        ),
        None,
    )
    if existing is not None:
        return existing
    ref = DocumentReferenceRead(
        source_document_id=dto.source_document_id,
        target_document_id=dto.target_document_id,
        reference_context=dto.reference_context,
    )
    rows.append(ref)
    return ref
