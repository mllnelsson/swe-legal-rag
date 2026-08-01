from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai import EmbeddingProvider
from shared.config import EMBEDDING_DIMENSION
from shared.pipeline import run_pipeline_step
from shared.repositories import ChunkRepo, TaskRepo
from worker_embed.errors import (
    EmbeddingCountMismatchError,
    EmbeddingDimensionError,
    NoChunksError,
)

logger = logging.getLogger(__name__)


async def process_embedding(
    document_id: UUID,
    task_id: UUID,
    chunk_repo: ChunkRepo,
    task_repo: TaskRepo,
    embedding_provider: EmbeddingProvider,
    session: AsyncSession,
    passage_prefix: str,
) -> None:
    """Embed every chunk of a document.

    `passage_prefix` is the document side of the embedding model's asymmetric
    prefix pair (`ai.get_embedding_prefixes`). It has no default: prefixing only
    one side of an asymmetric model puts queries and passages in systematically
    offset regions of the space, and that is precisely what a forgotten default
    would reintroduce. Pass `""` for a model that uses no prefixes.
    """

    async def body() -> None:
        chunks = await chunk_repo.get_by_document_id(session, document_id)
        if not chunks:
            raise NoChunksError(
                f"No chunks found for document {document_id} — chunk worker must run first"
            )

        texts = [
            passage_prefix + (chunk.contextual_text or chunk.chunk_text)
            for chunk in chunks
        ]

        vectors = await embedding_provider.embed(texts)

        if len(vectors) != len(chunks):
            raise EmbeddingCountMismatchError(
                f"Embedding count mismatch: expected {len(chunks)}, got {len(vectors)}"
            )

        for vector in vectors:
            if len(vector) != EMBEDDING_DIMENSION:
                raise EmbeddingDimensionError(
                    f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {len(vector)}"
                )

        updates = [(chunk.id, vector) for chunk, vector in zip(chunks, vectors)]
        await chunk_repo.update_embeddings(session, updates)

        logger.info("Embedded %d chunks for document %s", len(chunks), document_id)

    # Embedding is the terminal step: no next stage to publish. Failures re-raise
    # so the message can be redelivered.
    await run_pipeline_step(
        task_repo=task_repo,
        session=session,
        task_id=task_id,
        document_id=document_id,
        next_step=None,
        body=body,
        reraise=True,
    )
