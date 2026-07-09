from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.dtos.chunk import ChunkRead
from shared.dtos.document import DocumentRead
from shared.dtos.task import TaskRead
from worker_chunk.service import process_chunking

_NOW = datetime.now(tz=timezone.utc)


def _make_document(raw_text: str | None = "Swedish legal text.") -> DocumentRead:
    return DocumentRead(
        id=uuid.uuid4(),
        source_url="https://example.com/doc.pdf",
        gcs_uri=None,
        raw_text=raw_text,
        summary=None,
        case_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_task(status: str = "pending") -> TaskRead:
    return TaskRead(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        step="chunk",
        status=status,
        error_message=None,
        started_at=None,
        completed_at=None,
    )


def _make_chunk_read(document_id: uuid.UUID, index: int) -> ChunkRead:
    return ChunkRead(
        id=uuid.uuid4(),
        document_id=document_id,
        chunk_index=index,
        chunk_text="text",
        contextual_text="summary\n\n---\n\ntext",
        embedding=None,
        created_at=_NOW,
    )


class TestProcessChunkingSuccess:
    async def test_updates_document_summary(self) -> None:
        document = _make_document("Short legal text.")
        task = _make_task()
        embed_task = _make_task(status="pending")
        embed_task = TaskRead(**{**embed_task.model_dump(), "step": "embed"})

        document_repo = MagicMock()
        document_repo.get_by_id = AsyncMock(return_value=document)
        document_repo.update = AsyncMock(return_value=document)

        chunk_repo = MagicMock()
        chunk_repo.delete_by_document_id = AsyncMock(return_value=0)
        chunk_repo.bulk_create = AsyncMock(return_value=[])

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)
        task_repo.create = AsyncMock(return_value=embed_task)

        publisher = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        canned_summary = "Sammanfattning av målet."

        with patch(
            "worker_chunk.service.summarize_document", new=AsyncMock()
        ) as mock_summarize:
            from ai.dtos import SummarizeResult

            mock_summarize.return_value = SummarizeResult(summary=canned_summary)
            await process_chunking(
                document_id=document.id,
                task_id=task.id,
                document_repo=document_repo,
                chunk_repo=chunk_repo,
                task_repo=task_repo,
                queue_publisher=publisher,
                session=session,
            )

        document_repo.update.assert_awaited_once()
        call_args = document_repo.update.call_args
        assert call_args[0][1].summary == canned_summary

    async def test_deletes_existing_chunks_before_insert(self) -> None:
        document = _make_document("Legal text.")
        task = _make_task()
        embed_task = TaskRead(**{**_make_task().model_dump(), "step": "embed"})

        document_repo = MagicMock()
        document_repo.get_by_id = AsyncMock(return_value=document)
        document_repo.update = AsyncMock(return_value=document)

        chunk_repo = MagicMock()
        chunk_repo.delete_by_document_id = AsyncMock(return_value=0)
        chunk_repo.bulk_create = AsyncMock(return_value=[])

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)
        task_repo.create = AsyncMock(return_value=embed_task)

        publisher = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        with patch(
            "worker_chunk.service.summarize_document", new=AsyncMock()
        ) as mock_summarize:
            from ai.dtos import SummarizeResult

            mock_summarize.return_value = SummarizeResult(summary="Summary.")
            await process_chunking(
                document_id=document.id,
                task_id=task.id,
                document_repo=document_repo,
                chunk_repo=chunk_repo,
                task_repo=task_repo,
                queue_publisher=publisher,
                session=session,
            )

        chunk_repo.delete_by_document_id.assert_awaited_once_with(document.id)

    async def test_contextual_text_starts_with_summary(self) -> None:
        document = _make_document(
            "Kyrkoherden överklagade beslutet. Nämnden avslår överklagandet. Skälen framgår nedan."
        )
        task = _make_task()
        embed_task = TaskRead(**{**_make_task().model_dump(), "step": "embed"})

        captured_dtos: list = []

        async def capture_bulk_create(dtos: list) -> list:
            captured_dtos.extend(dtos)
            return []

        document_repo = MagicMock()
        document_repo.get_by_id = AsyncMock(return_value=document)
        document_repo.update = AsyncMock(return_value=document)

        chunk_repo = MagicMock()
        chunk_repo.delete_by_document_id = AsyncMock(return_value=0)
        chunk_repo.bulk_create = AsyncMock(side_effect=capture_bulk_create)

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)
        task_repo.create = AsyncMock(return_value=embed_task)

        publisher = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        canned_summary = "Kyrkoherden överklagade och nämnden avslog."

        with patch(
            "worker_chunk.service.summarize_document", new=AsyncMock()
        ) as mock_summarize:
            from ai.dtos import SummarizeResult

            mock_summarize.return_value = SummarizeResult(summary=canned_summary)
            await process_chunking(
                document_id=document.id,
                task_id=task.id,
                document_repo=document_repo,
                chunk_repo=chunk_repo,
                task_repo=task_repo,
                queue_publisher=publisher,
                session=session,
            )

        assert len(captured_dtos) > 0
        for dto in captured_dtos:
            assert dto.contextual_text is not None
            assert dto.contextual_text.startswith(canned_summary)

    async def test_publishes_to_embed_queue(self) -> None:
        document = _make_document("Legal text.")
        task = _make_task()
        embed_task = TaskRead(**{**_make_task().model_dump(), "step": "embed"})

        document_repo = MagicMock()
        document_repo.get_by_id = AsyncMock(return_value=document)
        document_repo.update = AsyncMock(return_value=document)

        chunk_repo = MagicMock()
        chunk_repo.delete_by_document_id = AsyncMock(return_value=0)
        chunk_repo.bulk_create = AsyncMock(return_value=[])

        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)
        task_repo.create = AsyncMock(return_value=embed_task)

        publisher = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        with patch(
            "worker_chunk.service.summarize_document", new=AsyncMock()
        ) as mock_summarize:
            from ai.dtos import SummarizeResult

            mock_summarize.return_value = SummarizeResult(summary="Summary.")
            await process_chunking(
                document_id=document.id,
                task_id=task.id,
                document_repo=document_repo,
                chunk_repo=chunk_repo,
                task_repo=task_repo,
                queue_publisher=publisher,
                session=session,
                next_topic="embed",
            )

        publisher.publish.assert_called_once()
        call_args = publisher.publish.call_args
        assert call_args[0][0] == "embed"


class TestProcessChunkingErrorCases:
    async def test_document_not_found_marks_task_failed(self) -> None:
        task = _make_task()

        document_repo = MagicMock()
        document_repo.get_by_id = AsyncMock(return_value=None)

        chunk_repo = MagicMock()
        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        publisher = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        await process_chunking(
            document_id=uuid.uuid4(),
            task_id=task.id,
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            queue_publisher=publisher,
            session=session,
        )

        update_calls = task_repo.update_status.call_args_list
        statuses = [c[0][1].status for c in update_calls]
        assert "failed" in statuses

    async def test_document_without_raw_text_marks_task_failed(self) -> None:
        document = _make_document(raw_text=None)
        task = _make_task()

        document_repo = MagicMock()
        document_repo.get_by_id = AsyncMock(return_value=document)

        chunk_repo = MagicMock()
        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)

        publisher = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        await process_chunking(
            document_id=document.id,
            task_id=task.id,
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            queue_publisher=publisher,
            session=session,
        )

        update_calls = task_repo.update_status.call_args_list
        statuses = [c[0][1].status for c in update_calls]
        assert "failed" in statuses

    async def test_already_completed_task_is_skipped(self) -> None:
        task = _make_task(status="completed")

        document_repo = MagicMock()
        document_repo.get_by_id = AsyncMock()

        chunk_repo = MagicMock()
        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)

        publisher = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()

        await process_chunking(
            document_id=uuid.uuid4(),
            task_id=task.id,
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            queue_publisher=publisher,
            session=session,
        )

        document_repo.get_by_id.assert_not_awaited()

    async def test_summarize_error_marks_task_failed_and_reraises(self) -> None:
        document = _make_document("Legal text.")
        task = _make_task()

        document_repo = MagicMock()
        document_repo.get_by_id = AsyncMock(return_value=document)
        document_repo.update = AsyncMock()

        chunk_repo = MagicMock()
        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update_status = AsyncMock(return_value=task)
        task_repo.create = AsyncMock()

        publisher = MagicMock()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        with patch(
            "worker_chunk.service.summarize_document", new=AsyncMock()
        ) as mock_summarize:
            mock_summarize.side_effect = RuntimeError("LLM unavailable")
            with pytest.raises(RuntimeError, match="LLM unavailable"):
                await process_chunking(
                    document_id=document.id,
                    task_id=task.id,
                    document_repo=document_repo,
                    chunk_repo=chunk_repo,
                    task_repo=task_repo,
                    queue_publisher=publisher,
                    session=session,
                )

        update_calls = task_repo.update_status.call_args_list
        statuses = [c[0][1].status for c in update_calls]
        assert "failed" in statuses
