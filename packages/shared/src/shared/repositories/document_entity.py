import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document_entity import DocumentEntityCreate, DocumentEntityRead
from shared.enums import EntityRelevance
from shared.models.document_entity import DocumentEntity


async def create(
    session: AsyncSession, dto: DocumentEntityCreate
) -> DocumentEntityRead:
    de = DocumentEntity(
        document_id=dto.document_id, entity_id=dto.entity_id, relevance=dto.relevance
    )
    session.add(de)
    await session.flush()
    await session.refresh(de)
    return DocumentEntityRead.model_validate(de)


async def get_by_document_id(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentEntityRead]:
    result = await session.execute(
        select(DocumentEntity).where(DocumentEntity.document_id == document_id)
    )
    return [DocumentEntityRead.model_validate(row) for row in result.scalars()]


async def upsert(
    session: AsyncSession, dto: DocumentEntityCreate
) -> DocumentEntityRead:
    result = await session.execute(
        select(DocumentEntity).where(
            DocumentEntity.document_id == dto.document_id,
            DocumentEntity.entity_id == dto.entity_id,
        )
    )
    de = result.scalar_one_or_none()
    if de is None:
        de = DocumentEntity(
            document_id=dto.document_id,
            entity_id=dto.entity_id,
            relevance=dto.relevance,
        )
        session.add(de)
        await session.flush()
        await session.refresh(de)
    elif dto.relevance == EntityRelevance.PRIMARY and (
        de.relevance != EntityRelevance.PRIMARY
    ):
        de.relevance = EntityRelevance.PRIMARY
        await session.flush()
        await session.refresh(de)
    return DocumentEntityRead.model_validate(de)


async def get_by_entity_id(
    session: AsyncSession, entity_id: uuid.UUID
) -> list[DocumentEntityRead]:
    result = await session.execute(
        select(DocumentEntity).where(DocumentEntity.entity_id == entity_id)
    )
    return [DocumentEntityRead.model_validate(row) for row in result.scalars()]
