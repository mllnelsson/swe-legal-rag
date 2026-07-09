import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.unresolved_reference import (
    UnresolvedReferenceCreate,
    UnresolvedReferenceRead,
)
from shared.models.unresolved_reference import UnresolvedReference


async def upsert(
    session: AsyncSession, dto: UnresolvedReferenceCreate
) -> UnresolvedReferenceRead:
    result = await session.execute(
        select(UnresolvedReference).where(
            UnresolvedReference.source_document_id == dto.source_document_id,
            UnresolvedReference.target_case_number == dto.target_case_number,
        )
    )
    ref = result.scalar_one_or_none()
    if ref is None:
        ref = UnresolvedReference(
            source_document_id=dto.source_document_id,
            target_case_number=dto.target_case_number,
            reference_context=dto.reference_context,
        )
        session.add(ref)
        await session.flush()
        await session.refresh(ref)
    return UnresolvedReferenceRead.model_validate(ref)


async def get_by_target_case_number(
    session: AsyncSession, case_number: str
) -> list[UnresolvedReferenceRead]:
    result = await session.execute(
        select(UnresolvedReference).where(
            UnresolvedReference.target_case_number == case_number
        )
    )
    return [UnresolvedReferenceRead.model_validate(row) for row in result.scalars()]


async def delete(session: AsyncSession, ref_id: uuid.UUID) -> None:
    ref = await session.get(UnresolvedReference, ref_id)
    if ref is not None:
        await session.delete(ref)
        await session.flush()
