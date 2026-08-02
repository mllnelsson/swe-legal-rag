from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai import SPECIAL_TOKEN_COUNT, CountTokens, EmbeddingProvider
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
    expected_dimension: int,
    count_tokens: CountTokens,
    max_input_tokens: int,
) -> None:
    """Embed every chunk of a document.

    `passage_prefix` is the document side of the embedding model's asymmetric
    prefix pair (`ai.get_embedding_prefixes`). It has no default: prefixing only
    one side of an asymmetric model puts queries and passages in systematically
    offset regions of the space, and that is precisely what a forgotten default
    would reintroduce. Pass `""` for a model that uses no prefixes.

    `expected_dimension` comes from the same resolved `EmbeddingConfig` as the
    provider, so this checks the vectors against the width that provider was
    configured for rather than against a process-wide constant that nothing
    ties to it. `ai.verify_embedding_dimension` has already reconciled that
    width with `shared.config.EMBEDDING_DIMENSION` at startup.

    An input longer than `max_input_tokens` is *warned about and embedded anyway*.
    The embedding model truncates it silently, so the warning is the only signal
    that a chunk's tail never reached its vector — but one over-long chunk is
    degraded retrieval for that chunk alone, whereas raising would fail the
    document's terminal step and have the message redelivered forever. The chunk
    worker is where the length is actually decided; this is the check that says so
    out loud.
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

        for chunk, text in zip(chunks, texts):
            length = count_tokens(text) + SPECIAL_TOKEN_COUNT
            if length > max_input_tokens:
                logger.warning(
                    "Chunk %s (document %s, index %d) is %d tokens and will be "
                    "silently truncated to %d by the embedding model",
                    chunk.id,
                    document_id,
                    chunk.chunk_index,
                    length,
                    max_input_tokens,
                )

        vectors = await embedding_provider.embed(texts)

        if len(vectors) != len(chunks):
            raise EmbeddingCountMismatchError(
                f"Embedding count mismatch: expected {len(chunks)}, got {len(vectors)}"
            )

        for vector in vectors:
            if len(vector) != expected_dimension:
                raise EmbeddingDimensionError(
                    f"Embedding dimension mismatch: expected {expected_dimension}, got {len(vector)}"
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
