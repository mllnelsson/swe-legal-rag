import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.chunk import ChunkCreate, ChunkRead
from shared.models.chunk import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, dtos: list[ChunkCreate]) -> list[ChunkRead]:
        chunks = [
            Chunk(
                document_id=dto.document_id,
                chunk_index=dto.chunk_index,
                chunk_text=dto.chunk_text,
                contextual_text=dto.contextual_text,
                embedding=dto.embedding,
            )
            for dto in dtos
        ]
        self._session.add_all(chunks)
        await self._session.flush()
        for chunk in chunks:
            await self._session.refresh(chunk)
        return [ChunkRead.model_validate(c) for c in chunks]

    async def get_by_document_id(self, document_id: uuid.UUID) -> list[ChunkRead]:
        result = await self._session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        )
        return [ChunkRead.model_validate(row) for row in result.scalars()]

    async def update_embeddings(self, updates: list[tuple[uuid.UUID, list[float]]]) -> None:
        for chunk_id, embedding in updates:
            stmt = update(Chunk).where(Chunk.id == chunk_id).values(embedding=embedding)
            await self._session.execute(stmt)

    async def delete_by_document_id(self, document_id: uuid.UUID) -> int:
        from typing import cast

        from sqlalchemy.engine import CursorResult

        result = cast(
            CursorResult,
            await self._session.execute(delete(Chunk).where(Chunk.document_id == document_id)),
        )
        return result.rowcount
