from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from _fsstore import now, store_of
from shared.dtos.document import DocumentCreate, DocumentRead, DocumentUpdate


def _rows(session: AsyncSession) -> list[DocumentRead]:
    return store_of(session).rows["documents"]


async def create(session: AsyncSession, dto: DocumentCreate) -> DocumentRead:
    created_at = now()
    doc = DocumentRead(
        id=uuid4(),
        source_url=dto.source_url,
        gcs_uri=None,
        raw_text=None,
        summary=None,
        case_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=created_at,
        updated_at=created_at,
    )
    _rows(session).append(doc)
    return doc


async def get_by_id(session: AsyncSession, document_id: UUID) -> DocumentRead | None:
    return next((d for d in _rows(session) if d.id == document_id), None)


async def get_by_source_url(
    session: AsyncSession, source_url: str
) -> DocumentRead | None:
    return next((d for d in _rows(session) if d.source_url == source_url), None)


async def get_by_case_number(
    session: AsyncSession, case_number: str
) -> DocumentRead | None:
    return next((d for d in _rows(session) if d.case_number == case_number), None)


async def update(
    session: AsyncSession, document_id: UUID, dto: DocumentUpdate
) -> DocumentRead | None:
    rows = _rows(session)
    for i, doc in enumerate(rows):
        if doc.id == document_id:
            changes = dto.model_dump(exclude_none=True)
            changes["updated_at"] = now()
            rows[i] = doc.model_copy(update=changes)
            return rows[i]
    return None
