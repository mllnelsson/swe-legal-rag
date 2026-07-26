import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.chunk import ChunkCreate, ChunkRead
from shared.dtos.search import ChunkSearchResult
from shared.enums import ChunkSection
from shared.models.chunk import Chunk

DEFAULT_SEARCH_LIMIT = 20

# Which parts of a document a search may draw from; None means every part.
Sections = Sequence[ChunkSection] | None


def _row_to_search_result(row: Any) -> ChunkSearchResult:
    # row is a SQLAlchemy Row with a Chunk entity and a labelled "score" column.
    chunk = row.Chunk
    return ChunkSearchResult(
        id=chunk.id,
        document_id=chunk.document_id,
        chunk_text=chunk.chunk_text,
        chunk_index=chunk.chunk_index,
        score=float(row.score),
        section=ChunkSection(chunk.section),
        appendix_label=chunk.appendix_label,
    )


def _restrict(
    stmt: Select[Any], document_ids: list[uuid.UUID] | None, sections: Sections
) -> Select[Any]:
    """Apply the two optional predicates both searches share.

    ``sections=None`` means "no restriction", which keeps the pre-segmentation
    behaviour available for callers that genuinely want appendices too.
    """
    if document_ids is not None:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))
    if sections is not None:
        stmt = stmt.where(Chunk.section.in_([s.value for s in sections]))
    return stmt


async def bulk_create(
    session: AsyncSession, dtos: list[ChunkCreate]
) -> list[ChunkRead]:
    chunks = [
        Chunk(
            document_id=dto.document_id,
            chunk_index=dto.chunk_index,
            chunk_text=dto.chunk_text,
            contextual_text=dto.contextual_text,
            embedding=dto.embedding,
            section=dto.section.value,
            appendix_label=dto.appendix_label,
        )
        for dto in dtos
    ]
    session.add_all(chunks)
    await session.flush()
    for chunk in chunks:
        await session.refresh(chunk)
    return [ChunkRead.model_validate(c) for c in chunks]


async def get_by_document_id(
    session: AsyncSession, document_id: uuid.UUID
) -> list[ChunkRead]:
    result = await session.execute(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
    )
    return [ChunkRead.model_validate(row) for row in result.scalars()]


async def update_embeddings(
    session: AsyncSession, updates: list[tuple[uuid.UUID, list[float]]]
) -> None:
    for chunk_id, embedding in updates:
        stmt = update(Chunk).where(Chunk.id == chunk_id).values(embedding=embedding)
        await session.execute(stmt)


async def delete_by_document_id(session: AsyncSession, document_id: uuid.UUID) -> int:
    result = cast(
        CursorResult,
        await session.execute(delete(Chunk).where(Chunk.document_id == document_id)),
    )
    return result.rowcount


async def vector_search(
    session: AsyncSession,
    embedding: list[float],
    document_ids: list[uuid.UUID] | None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    sections: Sections = None,
) -> list[ChunkSearchResult]:
    distance = Chunk.embedding.cosine_distance(embedding).label("score")
    stmt = (
        select(Chunk, distance)
        .where(Chunk.embedding.isnot(None))
        .order_by(distance)
        .limit(limit)
    )
    result = await session.execute(_restrict(stmt, document_ids, sections))
    return [_row_to_search_result(row) for row in result.all()]


async def text_search(
    session: AsyncSession,
    query: str,
    document_ids: list[uuid.UUID] | None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    sections: Sections = None,
) -> list[ChunkSearchResult]:
    tsquery = func.websearch_to_tsquery("swedish", query)
    rank = func.ts_rank(Chunk.tsv, tsquery).label("score")
    stmt = (
        select(Chunk, rank)
        .where(Chunk.tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    result = await session.execute(_restrict(stmt, document_ids, sections))
    return [_row_to_search_result(row) for row in result.all()]
