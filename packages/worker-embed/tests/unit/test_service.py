from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.config import EMBEDDING_DIMENSION
from shared.enums import ChunkSection
from shared.dtos.chunk import ChunkRead
from shared.dtos.task import TaskRead
from worker_embed.errors import (
    EmbeddingCountMismatchError,
    EmbeddingDimensionError,
    NoChunksError,
)
from worker_embed.service import process_embedding

_NOW = datetime.now(tz=timezone.utc)
# Derived from config so the suite follows a model/dimension change automatically.
_EMBEDDING_DIM = EMBEDDING_DIMENSION


def _count_words(text: str) -> int:
    """Words stand in for the embedding model's tokens.

    The service takes its counter as a parameter so the unit suite never loads a
    tokenizer.
    """
    return len(text.split())


# Generous enough that only the tests about the length warning trip it.
_MAX_INPUT_TOKENS = 512


def _make_chunk(
    document_id: uuid.UUID, index: int, contextual_text: str | None = "ctx text"
) -> ChunkRead:
    return ChunkRead(
        id=uuid.uuid4(),
        document_id=document_id,
        chunk_index=index,
        chunk_text="raw chunk text",
        contextual_text=contextual_text,
        embedding=[0.0] * _EMBEDDING_DIM,
        section=ChunkSection.BODY,
        appendix_label=None,
        created_at=_NOW,
    )


def _make_task(status: str = "pending") -> TaskRead:
    return TaskRead(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        step="embed",
        status=status,
        error_message=None,
        started_at=None,
        completed_at=None,
    )


def _make_vectors(count: int, dim: int = _EMBEDDING_DIM) -> list[list[float]]:
    return [[float(i) / 1000] * dim for i in range(count)]


class TestPassagePrefix:
    """The document half of the embedding model's asymmetric prefix pair.

    e5 is trained with `query: ` on one side and `passage: ` on the other.
    Applying it to only one side is worse than applying it to neither, so the
    parameter is required and these tests pin both directions.
    """

    async def _embed_one_chunk(self, passage_prefix: str) -> MagicMock:
        document_id = uuid.uuid4()
        task = _make_task()

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(
            return_value=[_make_chunk(document_id, 0, contextual_text="ctx text")]
        )
        chunk_repo.update_embeddings = AsyncMock()

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(return_value=_make_vectors(1))

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=embedding_provider,
            session=session,
            passage_prefix=passage_prefix,
            expected_dimension=_EMBEDDING_DIM,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )
        return embedding_provider

    async def test_prefix_is_prepended_to_every_passage(self) -> None:
        embedding_provider = await self._embed_one_chunk("passage: ")

        embedding_provider.embed.assert_awaited_once_with(["passage: ctx text"])

    async def test_empty_prefix_embeds_the_raw_text(self) -> None:
        """The correct setting for a model that uses no prefixes (bge-m3, jina)."""
        embedding_provider = await self._embed_one_chunk("")

        embedding_provider.embed.assert_awaited_once_with(["ctx text"])


class TestInputLengthWarning:
    """Over-long inputs are reported, never rejected and never trimmed.

    The embedding model truncates silently, so the warning is the only signal
    that a chunk's tail never reached its vector. Raising instead would fail the
    document's terminal step and have the message redelivered forever, so these
    tests pin "warn and proceed" against a later reader turning it into a raise.
    """

    async def _embed(
        self, contextual_text: str, max_input_tokens: int
    ) -> tuple[MagicMock, MagicMock, ChunkRead]:
        document_id = uuid.uuid4()
        task = _make_task()
        chunk = _make_chunk(document_id, 0, contextual_text=contextual_text)

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=[chunk])
        chunk_repo.update_embeddings = AsyncMock()

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(return_value=_make_vectors(1))

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=embedding_provider,
            session=session,
            passage_prefix="",
            expected_dimension=_EMBEDDING_DIM,
            count_tokens=_count_words,
            max_input_tokens=max_input_tokens,
        )
        return embedding_provider, task_repo, chunk

    async def test_over_long_input_is_warned_about_and_still_embedded(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        text = "ord " * 20

        with caplog.at_level(logging.WARNING, logger="worker_embed.service"):
            embedding_provider, task_repo, chunk = await self._embed(
                text, max_input_tokens=10
            )

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert str(chunk.id) in warnings[0].getMessage()
        # Untruncated: trimming here would hide the problem rather than report it.
        embedding_provider.embed.assert_awaited_once_with([text])
        statuses = [c[0][2].status for c in task_repo.update_status.call_args_list]
        assert "completed" in statuses
        assert "failed" not in statuses

    async def test_input_within_the_window_is_not_warned_about(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="worker_embed.service"):
            await self._embed("kort text", max_input_tokens=_MAX_INPUT_TOKENS)

        assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


class TestProcessEmbeddingSuccess:
    async def test_embeds_contextual_text_not_chunk_text(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task()
        chunks = [_make_chunk(document_id, 0, "contextual text")]

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=chunks)
        chunk_repo.update_embeddings = AsyncMock()

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(return_value=_make_vectors(1))

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=embedding_provider,
            session=session,
            passage_prefix="",
            expected_dimension=_EMBEDDING_DIM,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        embedding_provider.embed.assert_awaited_once_with(["contextual text"])

    async def test_batch_embed_called_once(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task()
        chunks = [_make_chunk(document_id, i) for i in range(3)]

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=chunks)
        chunk_repo.update_embeddings = AsyncMock()

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(return_value=_make_vectors(3))

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=embedding_provider,
            session=session,
            passage_prefix="",
            expected_dimension=_EMBEDDING_DIM,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        assert embedding_provider.embed.await_count == 1

    async def test_update_embeddings_called_with_correct_ids_and_vectors(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task()
        chunks = [_make_chunk(document_id, i) for i in range(2)]
        vectors = _make_vectors(2)

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=chunks)
        chunk_repo.update_embeddings = AsyncMock()

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(return_value=vectors)

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=embedding_provider,
            session=session,
            passage_prefix="",
            expected_dimension=_EMBEDDING_DIM,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        chunk_repo.update_embeddings.assert_awaited_once()
        call_args = chunk_repo.update_embeddings.call_args[0][1]
        assert call_args == [(chunks[0].id, vectors[0]), (chunks[1].id, vectors[1])]

    async def test_falls_back_to_chunk_text_when_contextual_text_is_none(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task()
        chunk = _make_chunk(document_id, 0, contextual_text=None)

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=[chunk])
        chunk_repo.update_embeddings = AsyncMock()

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(return_value=_make_vectors(1))

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=embedding_provider,
            session=session,
            passage_prefix="",
            expected_dimension=_EMBEDDING_DIM,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        embedding_provider.embed.assert_awaited_once_with(["raw chunk text"])


class TestProcessEmbeddingErrorCases:
    async def test_no_chunks_raises_embedding_error(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task()

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=[])

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        with pytest.raises(NoChunksError, match="No chunks found"):
            await process_embedding(
                document_id=document_id,
                task_id=task.id,
                chunk_repo=chunk_repo,
                task_repo=task_repo,
                embedding_provider=embedding_provider,
                session=session,
                passage_prefix="",
                expected_dimension=_EMBEDDING_DIM,
                count_tokens=_count_words,
                max_input_tokens=_MAX_INPUT_TOKENS,
            )

        update_calls = task_repo.update_status.call_args_list
        statuses = [c[0][2].status for c in update_calls]
        assert "failed" in statuses

    async def test_dimension_mismatch_raises_embedding_error(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task()
        chunks = [_make_chunk(document_id, 0)]

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=chunks)

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(return_value=[[0.0] * 512])

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        with pytest.raises(EmbeddingDimensionError, match="dimension"):
            await process_embedding(
                document_id=document_id,
                task_id=task.id,
                chunk_repo=chunk_repo,
                task_repo=task_repo,
                embedding_provider=embedding_provider,
                session=session,
                passage_prefix="",
                expected_dimension=_EMBEDDING_DIM,
                count_tokens=_count_words,
                max_input_tokens=_MAX_INPUT_TOKENS,
            )

        update_calls = task_repo.update_status.call_args_list
        statuses = [c[0][2].status for c in update_calls]
        assert "failed" in statuses

    async def test_vector_count_mismatch_raises_embedding_error(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task()
        chunks = [_make_chunk(document_id, i) for i in range(3)]

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=chunks)

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(return_value=_make_vectors(2))

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        with pytest.raises(EmbeddingCountMismatchError, match="mismatch"):
            await process_embedding(
                document_id=document_id,
                task_id=task.id,
                chunk_repo=chunk_repo,
                task_repo=task_repo,
                embedding_provider=embedding_provider,
                session=session,
                passage_prefix="",
                expected_dimension=_EMBEDDING_DIM,
                count_tokens=_count_words,
                max_input_tokens=_MAX_INPUT_TOKENS,
            )

        update_calls = task_repo.update_status.call_args_list
        statuses = [c[0][2].status for c in update_calls]
        assert "failed" in statuses

    async def test_embedding_client_failure_propagates(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task()
        chunks = [_make_chunk(document_id, 0)]

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id = AsyncMock(return_value=chunks)

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        embedding_provider.embed = AsyncMock(
            side_effect=RuntimeError("Model unavailable")
        )

        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        with pytest.raises(RuntimeError, match="Model unavailable"):
            await process_embedding(
                document_id=document_id,
                task_id=task.id,
                chunk_repo=chunk_repo,
                task_repo=task_repo,
                embedding_provider=embedding_provider,
                session=session,
                passage_prefix="",
                expected_dimension=_EMBEDDING_DIM,
                count_tokens=_count_words,
                max_input_tokens=_MAX_INPUT_TOKENS,
            )

        update_calls = task_repo.update_status.call_args_list
        statuses = [c[0][2].status for c in update_calls]
        assert "failed" in statuses

    async def test_already_completed_task_is_skipped(self) -> None:
        document_id = uuid.uuid4()
        task = _make_task(status="completed")

        chunk_repo = MagicMock()
        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)

        embedding_provider = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()

        await process_embedding(
            document_id=document_id,
            task_id=task.id,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            embedding_provider=embedding_provider,
            session=session,
            passage_prefix="",
            expected_dimension=_EMBEDDING_DIM,
            count_tokens=_count_words,
            max_input_tokens=_MAX_INPUT_TOKENS,
        )

        chunk_repo.get_by_document_id = MagicMock()
        assert (
            not hasattr(chunk_repo.get_by_document_id, "await_count")
            or not chunk_repo.get_by_document_id.called
        )
