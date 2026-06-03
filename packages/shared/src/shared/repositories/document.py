import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate, DocumentRead, DocumentUpdate
from shared.models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, dto: DocumentCreate) -> DocumentRead:
        doc = Document(source_url=dto.source_url)
        self._session.add(doc)
        await self._session.flush()
        await self._session.refresh(doc)
        return DocumentRead.model_validate(doc)

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentRead | None:
        doc = await self._session.get(Document, document_id)
        return DocumentRead.model_validate(doc) if doc else None

    async def get_by_source_url(self, source_url: str) -> DocumentRead | None:
        result = await self._session.execute(select(Document).where(Document.source_url == source_url))
        doc = result.scalar_one_or_none()
        return DocumentRead.model_validate(doc) if doc else None

    async def update(self, document_id: uuid.UUID, dto: DocumentUpdate) -> DocumentRead | None:
        doc = await self._session.get(Document, document_id)
        if doc is None:
            return None
        for field, value in dto.model_dump(exclude_none=True).items():
            setattr(doc, field, value)
        await self._session.flush()
        await self._session.refresh(doc)
        return DocumentRead.model_validate(doc)

    async def list(self, skip: int = 0, limit: int = 100) -> list[DocumentRead]:
        result = await self._session.execute(select(Document).offset(skip).limit(limit))
        return [DocumentRead.model_validate(row) for row in result.scalars()]
