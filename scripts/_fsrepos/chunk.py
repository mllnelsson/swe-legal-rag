from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from _fsstore import now, store_of
from shared.dtos.chunk import ChunkCreate, ChunkRead


def _rows(session: AsyncSession) -> list[ChunkRead]:
    return store_of(session).rows["chunks"]


async def bulk_create(
    session: AsyncSession, dtos: list[ChunkCreate]
) -> list[ChunkRead]:
    created_at = now()
    created = [
        ChunkRead(
            id=uuid4(),
            document_id=dto.document_id,
            chunk_index=dto.chunk_index,
            chunk_text=dto.chunk_text,
            contextual_text=dto.contextual_text,
            embedding=dto.embedding,
            section=dto.section,
            appendix_label=dto.appendix_label,
            created_at=created_at,
        )
        for dto in dtos
    ]
    _rows(session).extend(created)
    return created


async def get_by_document_id(
    session: AsyncSession, document_id: UUID
) -> list[ChunkRead]:
    chunks = [c for c in _rows(session) if c.document_id == document_id]
    return sorted(chunks, key=lambda c: c.chunk_index)


async def update_embeddings(
    session: AsyncSession, updates: list[tuple[UUID, list[float]]]
) -> None:
    by_id = dict(updates)
    rows = _rows(session)
    for i, chunk in enumerate(rows):
        if chunk.id in by_id:
            rows[i] = chunk.model_copy(update={"embedding": by_id[chunk.id]})


async def delete_by_document_id(session: AsyncSession, document_id: UUID) -> int:
    store = store_of(session)
    rows = store.rows["chunks"]
    keep = [c for c in rows if c.document_id != document_id]
    removed = len(rows) - len(keep)
    store.rows["chunks"] = keep
    return removed
