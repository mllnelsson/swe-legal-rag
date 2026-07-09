from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from _fsstore import now, store_of
from shared.dtos.unresolved_reference import (
    UnresolvedReferenceCreate,
    UnresolvedReferenceRead,
)


def _rows(session: AsyncSession) -> list[UnresolvedReferenceRead]:
    return store_of(session).rows["unresolved"]


async def upsert(
    session: AsyncSession, dto: UnresolvedReferenceCreate
) -> UnresolvedReferenceRead:
    rows = _rows(session)
    existing = next(
        (
            r
            for r in rows
            if r.source_document_id == dto.source_document_id
            and r.target_case_number == dto.target_case_number
        ),
        None,
    )
    if existing is not None:
        return existing
    ref = UnresolvedReferenceRead(
        id=uuid4(),
        source_document_id=dto.source_document_id,
        target_case_number=dto.target_case_number,
        reference_context=dto.reference_context,
        created_at=now(),
    )
    rows.append(ref)
    return ref


async def get_by_target_case_number(
    session: AsyncSession, case_number: str
) -> list[UnresolvedReferenceRead]:
    return [r for r in _rows(session) if r.target_case_number == case_number]


async def delete(session: AsyncSession, ref_id: UUID) -> None:
    store = store_of(session)
    store.rows["unresolved"] = [r for r in store.rows["unresolved"] if r.id != ref_id]
