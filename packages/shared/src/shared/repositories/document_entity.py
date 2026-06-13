import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document_entity import DocumentEntityCreate, DocumentEntityRead
from shared.models.document_entity import DocumentEntity


class DocumentEntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, dto: DocumentEntityCreate) -> DocumentEntityRead:
        de = DocumentEntity(document_id=dto.document_id, entity_id=dto.entity_id, relevance=dto.relevance)
        self._session.add(de)
        await self._session.flush()
        await self._session.refresh(de)
        return DocumentEntityRead.model_validate(de)

    async def get_by_document_id(self, document_id: uuid.UUID) -> list[DocumentEntityRead]:
        result = await self._session.execute(
            select(DocumentEntity).where(DocumentEntity.document_id == document_id)
        )
        return [DocumentEntityRead.model_validate(row) for row in result.scalars()]

    async def upsert(self, dto: DocumentEntityCreate) -> DocumentEntityRead:
        result = await self._session.execute(
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
            self._session.add(de)
            await self._session.flush()
            await self._session.refresh(de)
        elif dto.relevance == "primary" and de.relevance != "primary":
            de.relevance = "primary"
            await self._session.flush()
            await self._session.refresh(de)
        return DocumentEntityRead.model_validate(de)

    async def get_by_entity_id(self, entity_id: uuid.UUID) -> list[DocumentEntityRead]:
        result = await self._session.execute(
            select(DocumentEntity).where(DocumentEntity.entity_id == entity_id)
        )
        return [DocumentEntityRead.model_validate(row) for row in result.scalars()]
