import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document_reference import (
    DocumentReferenceCreate,
    DocumentReferenceRead,
)
from shared.models.document_reference import DocumentReference


async def create(
    session: AsyncSession, dto: DocumentReferenceCreate
) -> DocumentReferenceRead:
    ref = DocumentReference(
        source_document_id=dto.source_document_id,
        target_document_id=dto.target_document_id,
        reference_context=dto.reference_context,
    )
    session.add(ref)
    await session.flush()
    await session.refresh(ref)
    return DocumentReferenceRead.model_validate(ref)


async def upsert(
    session: AsyncSession, dto: DocumentReferenceCreate
) -> DocumentReferenceRead:
    result = await session.execute(
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
        session.add(ref)
        await session.flush()
        await session.refresh(ref)
    return DocumentReferenceRead.model_validate(ref)


async def get_by_source_document_id(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentReferenceRead]:
    result = await session.execute(
        select(DocumentReference).where(
            DocumentReference.source_document_id == document_id
        )
    )
    return [DocumentReferenceRead.model_validate(row) for row in result.scalars()]


async def get_by_target_document_id(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentReferenceRead]:
    result = await session.execute(
        select(DocumentReference).where(
            DocumentReference.target_document_id == document_id
        )
    )
    return [DocumentReferenceRead.model_validate(row) for row in result.scalars()]
