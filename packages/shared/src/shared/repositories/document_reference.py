import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document_reference import DocumentReferenceCreate, DocumentReferenceRead
from shared.models.document_reference import DocumentReference


class DocumentReferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, dto: DocumentReferenceCreate) -> DocumentReferenceRead:
        ref = DocumentReference(
            source_document_id=dto.source_document_id,
            target_document_id=dto.target_document_id,
            reference_context=dto.reference_context,
        )
        self._session.add(ref)
        await self._session.flush()
        await self._session.refresh(ref)
        return DocumentReferenceRead.model_validate(ref)

    async def upsert(self, dto: DocumentReferenceCreate) -> DocumentReferenceRead:
        result = await self._session.execute(
            select(DocumentReference).where(
                DocumentReference.source_document_id == dto.source_document_id,
                DocumentReference.target_document_id == dto.target_document_id,
            )
        )
        ref = result.scalar_one_or_none()
        if ref is None:
            ref = DocumentReference(
                source_document_id=dto.source_document_id,
                target_document_id=dto.target_document_id,
                reference_context=dto.reference_context,
            )
            self._session.add(ref)
            await self._session.flush()
            await self._session.refresh(ref)
        return DocumentReferenceRead.model_validate(ref)

    async def get_by_source_document_id(self, document_id: uuid.UUID) -> list[DocumentReferenceRead]:
        result = await self._session.execute(
            select(DocumentReference).where(DocumentReference.source_document_id == document_id)
        )
        return [DocumentReferenceRead.model_validate(row) for row in result.scalars()]

    async def get_by_target_document_id(self, document_id: uuid.UUID) -> list[DocumentReferenceRead]:
        result = await self._session.execute(
            select(DocumentReference).where(DocumentReference.target_document_id == document_id)
        )
        return [DocumentReferenceRead.model_validate(row) for row in result.scalars()]
