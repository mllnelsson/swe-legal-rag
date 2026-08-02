from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import EMBEDDING_DIMENSION
from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentCreate
from shared.dtos.task import TaskCreate
from shared.testing.pipeline import redrive_task
from shared.models.chunk import Chunk
from worker_embed.service import process_embedding

_SWEDISH_TEXT = "Nämnden beslutade att avslå överklagandet."
_CONTEXTUAL_TEXT = "Kyrkoherden överklagade beslutet.\n\n---\n\n" + _SWEDISH_TEXT

_PLACEHOLDER_EMBEDDING = [0.0] * EMBEDDING_DIMENSION


def _count_words(text: str) -> int:
    """Words, deliberately not the embedding model's tokenizer.

    This file tests the database round-trip; the real ruler would make the
    integration suite need the HuggingFace hub or a warm cache to start.
    """
    return len(text.split())


# Generous: nothing here is meant to trip the input-length warning.
_MAX_INPUT_TOKENS = 512


def _make_deterministic_vectors(count: int) -> list[list[float]]:
    return [[float(i + 1) / 1000] * EMBEDDING_DIMENSION for i in range(count)]


def _make_mock_embedding_provider(count: int) -> MagicMock:
    provider = MagicMock()
    provider.embed = AsyncMock(return_value=_make_deterministic_vectors(count))
    return provider


async def _create_test_chunks(
    document_repo,
    chunk_repo,
    session: AsyncSession,
    chunk_count: int = 2,
) -> tuple[UUID, list]:
    doc = await document_repo.create(
        session, DocumentCreate(source_url="https://example.com/test.pdf")
    )
    await session.flush()

    dtos = [
        ChunkCreate(
            document_id=doc.id,
            chunk_index=i,
            chunk_text=_SWEDISH_TEXT,
            contextual_text=_CONTEXTUAL_TEXT,
            embedding=_PLACEHOLDER_EMBEDDING,
        )
        for i in range(chunk_count)
    ]
    chunks = await chunk_repo.bulk_create(session, dtos)
    await session.commit()
    return doc.id, chunks


class TestEmbedPipelineEndToEnd:
    async def test_embeddings_are_populated(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session
        )
        task = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        provider = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        updated = await chunk_repo.get_by_document_id(session, document_id)
        for chunk in updated:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == EMBEDDING_DIMENSION

    async def test_embeddings_differ_from_placeholder(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session
        )
        task = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        provider = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        updated = await chunk_repo.get_by_document_id(session, document_id)
        for chunk in updated:
            assert chunk.embedding != _PLACEHOLDER_EMBEDDING

    async def test_tsv_is_populated(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session
        )
        task = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        provider = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        result = await session.execute(
            select(Chunk.tsv).where(Chunk.document_id == document_id)
        )
        tsvectors = result.scalars().all()
        assert all(tsv is not None for tsv in tsvectors)

    async def test_tsv_matches_swedish_query(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session
        )
        task = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        provider = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        result = await session.execute(
            text(
                "SELECT count(*) FROM chunks "
                "WHERE document_id = :doc_id "
                "AND tsv @@ to_tsquery('swedish', 'beslut')"
            ),
            {"doc_id": document_id},
        )
        count = result.scalar()
        assert count and count > 0

    async def test_task_marked_completed(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session
        )
        task = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        provider = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        updated_task = await task_repo.get_by_id(session, task.id)
        assert updated_task is not None
        assert updated_task.status == "completed"


class TestIndexFunctionality:
    async def test_hnsw_similarity_search_returns_results(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session
        )
        task = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        provider = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        query_vector = "[" + ",".join(["0.001"] * EMBEDDING_DIMENSION) + "]"
        result = await session.execute(
            text(
                f"SELECT id FROM chunks "
                f"WHERE document_id = :doc_id "
                f"ORDER BY embedding <-> '{query_vector}' "
                f"LIMIT 5"
            ),
            {"doc_id": document_id},
        )
        rows = result.fetchall()
        assert len(rows) > 0

    async def test_gin_full_text_search_returns_results(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session
        )
        task = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        provider = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        result = await session.execute(
            text(
                "SELECT id FROM chunks "
                "WHERE document_id = :doc_id "
                "AND tsv @@ to_tsquery('swedish', 'avslå')"
            ),
            {"doc_id": document_id},
        )
        rows = result.fetchall()
        assert len(rows) > 0


class TestEmbedPipelineIdempotency:
    async def test_rerun_overwrites_embeddings(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session
        )
        task1 = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        first_vectors = _make_deterministic_vectors(len(chunks))
        provider1 = MagicMock()
        provider1.embed = AsyncMock(return_value=first_vectors)
        await process_embedding(
            document_id=document_id,
            task_id=task1.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider1,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        await redrive_task(session, task_repo, task1.id)

        second_vectors = [[0.999] * EMBEDDING_DIMENSION for _ in chunks]
        provider2 = MagicMock()
        provider2.embed = AsyncMock(return_value=second_vectors)
        await process_embedding(
            document_id=document_id,
            task_id=task1.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider2,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        updated = await chunk_repo.get_by_document_id(session, document_id)
        for chunk in updated:
            assert chunk.embedding is not None
            assert chunk.embedding[0] == pytest.approx(0.999)

    async def test_rerun_does_not_create_duplicate_chunks(
        self,
        document_repo,
        chunk_repo,
        task_repo,
        session: AsyncSession,
    ) -> None:
        document_id, chunks = await _create_test_chunks(
            document_repo, chunk_repo, session, chunk_count=2
        )
        task1 = await task_repo.create(
            session, TaskCreate(document_id=document_id, step="embed", status="pending")
        )
        await session.commit()

        provider = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task1.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        await redrive_task(session, task_repo, task1.id)

        provider2 = _make_mock_embedding_provider(len(chunks))
        await process_embedding(
            document_id=document_id,
            task_id=task1.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=provider2,
            session=session,
            passage_prefix="",
            expected_dimension=EMBEDDING_DIMENSION,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        final_chunks = await chunk_repo.get_by_document_id(session, document_id)
        assert len(final_chunks) == len(chunks)
