from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai import EmbeddingProvider
from shared.config import EMBEDDING_DIMENSION
from shared.dtos.task import TaskStatusUpdate
from shared.repositories import ChunkRepo, TaskRepo

logger = logging.getLogger(__name__)


async def process_embedding(
    document_id: UUID,
    task_id: UUID,
    chunk_repo: ChunkRepo,
    task_repo: TaskRepo,
    embedding_provider: EmbeddingProvider,
    session: AsyncSession,
) -> None:
    task = await task_repo.get_by_id(session, task_id)
    if task is None or task.status == "completed":
        logger.info("Task %s already completed or not found, skipping", task_id)
        return

    await task_repo.update_status(
        session, task_id, TaskStatusUpdate(status="processing")
    )
    await session.commit()

    try:
        chunks = await chunk_repo.get_by_document_id(session, document_id)
        if not chunks:
            raise ValueError(
                f"No chunks found for document {document_id} — chunk worker must run first"
            )

        texts = [chunk.contextual_text or chunk.chunk_text for chunk in chunks]

        vectors = await embedding_provider.embed(texts)

        if len(vectors) != len(chunks):
            raise ValueError(
                f"Embedding count mismatch: expected {len(chunks)}, got {len(vectors)}"
            )

        for vector in vectors:
            if len(vector) != EMBEDDING_DIMENSION:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {len(vector)}"
                )

        updates = [(chunk.id, vector) for chunk, vector in zip(chunks, vectors)]
        await chunk_repo.update_embeddings(session, updates)

        await task_repo.update_status(
            session, task_id, TaskStatusUpdate(status="completed")
        )
        await session.commit()

        logger.info("Embedded %d chunks for document %s", len(chunks), document_id)

    except Exception as exc:
        await session.rollback()
        logger.error("Failed to embed document %s: %s", document_id, exc, exc_info=True)
        await task_repo.update_status(
            session,
            task_id,
            TaskStatusUpdate(status="failed", error_message=str(exc)),
        )
        await session.commit()
        raise
