import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.unresolved_reference import UnresolvedReferenceCreate, UnresolvedReferenceRead
from shared.models.unresolved_reference import UnresolvedReference


class UnresolvedReferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, dto: UnresolvedReferenceCreate) -> UnresolvedReferenceRead:
        result = await self._session.execute(
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
            self._session.add(ref)
            await self._session.flush()
            await self._session.refresh(ref)
        return UnresolvedReferenceRead.model_validate(ref)

    async def get_by_target_case_number(self, case_number: str) -> list[UnresolvedReferenceRead]:
        result = await self._session.execute(
            select(UnresolvedReference).where(UnresolvedReference.target_case_number == case_number)
        )
        return [UnresolvedReferenceRead.model_validate(row) for row in result.scalars()]

    async def delete(self, ref_id: uuid.UUID) -> None:
        ref = await self._session.get(UnresolvedReference, ref_id)
        if ref is not None:
            await self._session.delete(ref)
            await self._session.flush()
