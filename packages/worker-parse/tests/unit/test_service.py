from shared.enums import PipelineStep
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from shared.dtos.document import DocumentRead
from shared.dtos.task import TaskRead
from shared.queue.base import QueueMessage
from worker_parse.parser import ParseError
from worker_parse.service import process_parse


def _make_doc_read(
    document_id: uuid.UUID | None = None,
    gcs_uri: str | None = "gs://bucket/documents/x/original.pdf",
) -> DocumentRead:
    now = datetime.now(tz=timezone.utc)
    return DocumentRead(
        id=document_id or uuid.uuid4(),
        source_url="https://example.com/doc.pdf",
        source_document_id=None,
        source_headline=None,
        source_decision_number=None,
        source_published_at=None,
        gcs_uri=gcs_uri,
        raw_text=None,
        summary=None,
        case_number=None,
        decision_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=now,
        updated_at=now,
    )


def _make_task_read(
    document_id: uuid.UUID,
    step: str = "parse",
    status: str = "pending",
) -> TaskRead:
    return TaskRead(
        id=uuid.uuid4(),
        document_id=document_id,
        step=step,
        status=status,
        error_message=None,
        started_at=None,
        completed_at=None,
    )


def _make_deps(
    task: TaskRead | None,
    document: DocumentRead | None,
    pdf_bytes: bytes = b"PDF",
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    storage = MagicMock()
    storage.retrieve.return_value = pdf_bytes

    doc_repo = MagicMock()
    doc_repo.get_by_id = AsyncMock(return_value=document)
    doc_repo.update = AsyncMock()

    task_repo = MagicMock()
    task_repo.get_by_id = AsyncMock(return_value=task)
    task_repo.get_by_document_and_step = AsyncMock(return_value=None)
    task_repo.update_status = AsyncMock()
    if document is not None:
        task_repo.create = AsyncMock(
            return_value=_make_task_read(document.id, "metadata", "pending")
        )
    else:
        task_repo.create = AsyncMock()

    publisher = MagicMock()

    return session, storage, doc_repo, task_repo, publisher


async def _call_process_parse(
    document_id: uuid.UUID,
    task_id: uuid.UUID,
    session: MagicMock,
    storage: MagicMock,
    doc_repo: MagicMock,
    task_repo: MagicMock,
    publisher: MagicMock,
    parser: MagicMock,
) -> None:
    await process_parse(
        document_id=document_id,
        task_id=task_id,
        storage=storage,
        document_repo=doc_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        parser=parser,
        session=session,
        next_topic=PipelineStep.METADATA,
    )


async def test_happy_path_parses_and_publishes() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    session, storage, doc_repo, task_repo, publisher = _make_deps(
        task, doc, b"PDF_BYTES"
    )
    parser = MagicMock(return_value="parsed text")

    await _call_process_parse(
        doc.id, task.id, session, storage, doc_repo, task_repo, publisher, parser
    )

    parser.assert_called_once_with(b"PDF_BYTES")

    doc_repo.update.assert_called_once()
    _session, _doc_id, update_dto = doc_repo.update.call_args[0]
    assert _doc_id == doc.id
    assert update_dto.raw_text == "parsed text"

    status_calls = [call[0][2] for call in task_repo.update_status.call_args_list]
    assert status_calls[0].status == "processing"
    assert status_calls[-1].status == "completed"

    assert session.commit.call_count == 3

    publisher.publish.assert_called_once()
    topic, msg = publisher.publish.call_args[0]
    assert topic == "metadata"
    assert isinstance(msg, QueueMessage)
    assert msg.document_id == doc.id


async def test_parser_failure_marks_task_failed() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    session, storage, doc_repo, task_repo, publisher = _make_deps(task, doc)
    parser = MagicMock(side_effect=ParseError("corrupt PDF"))

    await _call_process_parse(
        doc.id, task.id, session, storage, doc_repo, task_repo, publisher, parser
    )

    status_calls = [call[0][2] for call in task_repo.update_status.call_args_list]
    assert status_calls[-1].status == "failed"
    assert "corrupt PDF" in status_calls[-1].error_message

    session.rollback.assert_called_once()
    publisher.publish.assert_not_called()


async def test_storage_failure_marks_task_failed() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    session, storage, doc_repo, task_repo, publisher = _make_deps(task, doc)
    storage.retrieve.side_effect = OSError("disk error")
    parser = MagicMock()

    await _call_process_parse(
        doc.id, task.id, session, storage, doc_repo, task_repo, publisher, parser
    )

    status_calls = [call[0][2] for call in task_repo.update_status.call_args_list]
    assert status_calls[-1].status == "failed"
    assert "disk error" in status_calls[-1].error_message

    session.rollback.assert_called_once()
    publisher.publish.assert_not_called()
    parser.assert_not_called()


async def test_document_not_found_marks_task_failed() -> None:
    doc_id = uuid.uuid4()
    task = _make_task_read(doc_id)
    session, storage, doc_repo, task_repo, publisher = _make_deps(task, document=None)
    parser = MagicMock()

    await _call_process_parse(
        doc_id, task.id, session, storage, doc_repo, task_repo, publisher, parser
    )

    status_calls = [call[0][2] for call in task_repo.update_status.call_args_list]
    assert status_calls[0].status == "processing"
    assert status_calls[-1].status == "failed"
    assert str(doc_id) in status_calls[-1].error_message

    publisher.publish.assert_not_called()
    parser.assert_not_called()
    session.rollback.assert_not_called()


async def test_already_completed_task_is_skipped() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id, status="completed")
    session, storage, doc_repo, task_repo, publisher = _make_deps(task, doc)
    parser = MagicMock()

    await _call_process_parse(
        doc.id, task.id, session, storage, doc_repo, task_repo, publisher, parser
    )

    task_repo.update_status.assert_not_called()
    session.commit.assert_not_called()
    publisher.publish.assert_not_called()
    parser.assert_not_called()


async def test_missing_gcs_uri_marks_task_failed() -> None:
    doc = _make_doc_read(gcs_uri=None)
    task = _make_task_read(doc.id)
    session, storage, doc_repo, task_repo, publisher = _make_deps(task, doc)
    parser = MagicMock()

    await _call_process_parse(
        doc.id, task.id, session, storage, doc_repo, task_repo, publisher, parser
    )

    status_calls = [call[0][2] for call in task_repo.update_status.call_args_list]
    assert status_calls[-1].status == "failed"

    publisher.publish.assert_not_called()
    parser.assert_not_called()
    session.rollback.assert_not_called()
