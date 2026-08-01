from shared.enums import PipelineStep
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import respx

from shared.dtos.document import DocumentRead
from shared.dtos.task import TaskRead
from shared.queue.base import QueueMessage
from worker_download.service import process_download


def _make_doc_read(
    source_url: str = "https://example.com/doc.pdf",
    gcs_uri: str | None = None,
) -> DocumentRead:
    now = datetime.now(tz=timezone.utc)
    return DocumentRead(
        id=uuid.uuid4(),
        source_url=source_url,
        source_document_id=None,
        source_headline=None,
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
    step: str = "download",
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


def _make_message(task_id: uuid.UUID, document_id: uuid.UUID) -> QueueMessage:
    return QueueMessage(task_id=task_id, document_id=document_id)


def _make_deps(
    task: TaskRead | None,
    document: DocumentRead | None,
    storage_uri: str = "gs://bucket/doc/original.pdf",
    max_retries: int = 2,
) -> tuple[dict, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    doc_repo = MagicMock()
    task_repo = MagicMock()
    storage = MagicMock()
    publisher = MagicMock()

    task_repo.get_by_id = AsyncMock(return_value=task)
    doc_repo.get_by_id = AsyncMock(return_value=document)
    task_repo.get_by_document_and_step = AsyncMock(return_value=None)
    task_repo.update_status = AsyncMock()
    doc_repo.update = AsyncMock()
    storage.store.return_value = storage_uri

    async def create_task(_session, dto):
        return _make_task_read(dto.document_id, dto.step, dto.status)

    task_repo.create = create_task

    kwargs = dict(
        session=session,
        document_repo=doc_repo,
        task_repo=task_repo,
        storage=storage,
        queue_publisher=publisher,
        timeout=5,
        max_retries=max_retries,
        rate_limit_delay=0,
        next_topic=PipelineStep.PARSE,
    )
    return kwargs, session, task_repo, doc_repo, storage, publisher


@patch("worker_download.service._download_pdf")
async def test_handle_message_happy_path(mock_download) -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    kwargs, session, task_repo, doc_repo, storage, publisher = _make_deps(task, doc)

    mock_download.return_value = b"PDF_CONTENT"
    storage.store.return_value = f"gs://bucket/documents/{doc.id}/original.pdf"

    msg = _make_message(task.id, doc.id)
    await process_download(msg, **kwargs)

    status_calls = task_repo.update_status.call_args_list
    assert status_calls[0][0][2].status == "processing"
    assert status_calls[1][0][2].status == "completed"

    storage.store.assert_called_once_with(
        f"documents/{doc.id}/original.pdf", b"PDF_CONTENT"
    )
    doc_repo.update.assert_called_once()

    assert session.commit.call_count == 3

    publisher.publish.assert_called_once()
    topic, message = publisher.publish.call_args[0]
    assert topic == "parse"
    assert isinstance(message, QueueMessage)
    assert message.document_id == doc.id


async def test_handle_message_skips_completed_task() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id, status="completed")
    kwargs, session, task_repo, doc_repo, storage, publisher = _make_deps(task, doc)

    msg = _make_message(task.id, doc.id)
    await process_download(msg, **kwargs)

    task_repo.update_status.assert_not_called()
    session.commit.assert_not_called()
    publisher.publish.assert_not_called()
    storage.store.assert_not_called()


async def test_handle_message_skips_missing_task() -> None:
    kwargs, session, task_repo, doc_repo, storage, publisher = _make_deps(
        task=None, document=None
    )

    msg = _make_message(uuid.uuid4(), uuid.uuid4())
    await process_download(msg, **kwargs)

    task_repo.update_status.assert_not_called()
    session.commit.assert_not_called()
    publisher.publish.assert_not_called()


async def test_handle_message_fails_on_missing_document() -> None:
    doc_id = uuid.uuid4()
    task = _make_task_read(doc_id)
    kwargs, session, task_repo, doc_repo, storage, publisher = _make_deps(
        task=task, document=None
    )

    msg = _make_message(task.id, doc_id)
    await process_download(msg, **kwargs)

    status_calls = task_repo.update_status.call_args_list
    assert status_calls[0][0][2].status == "processing"
    assert status_calls[1][0][2].status == "failed"
    assert str(doc_id) in status_calls[1][0][2].error_message
    assert session.commit.call_count == 2
    publisher.publish.assert_not_called()
    storage.store.assert_not_called()


@patch("worker_download.service._download_pdf")
async def test_handle_message_idempotent_with_existing_gcs_uri(mock_download) -> None:
    doc = _make_doc_read(gcs_uri="gs://bucket/existing.pdf")
    task = _make_task_read(doc.id)
    kwargs, session, task_repo, doc_repo, storage, publisher = _make_deps(task, doc)

    msg = _make_message(task.id, doc.id)
    await process_download(msg, **kwargs)

    mock_download.assert_not_called()
    storage.store.assert_not_called()

    publisher.publish.assert_called_once()
    topic, message = publisher.publish.call_args[0]
    assert topic == "parse"
    assert message.document_id == doc.id

    status_calls = task_repo.update_status.call_args_list
    assert status_calls[-1][0][2].status == "completed"


@patch("worker_download.service._download_pdf")
async def test_handle_message_marks_failed_on_http_error(mock_download) -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    kwargs, session, task_repo, doc_repo, storage, publisher = _make_deps(task, doc)

    mock_download.side_effect = httpx.ConnectError("Connection refused")

    msg = _make_message(task.id, doc.id)
    await process_download(msg, **kwargs)

    storage.store.assert_not_called()
    publisher.publish.assert_not_called()

    status_calls = task_repo.update_status.call_args_list
    assert status_calls[-1][0][2].status == "failed"
    assert "Connection refused" in status_calls[-1][0][2].error_message

    session.rollback.assert_called_once()


@patch("worker_download.service._download_pdf")
async def test_handle_message_marks_failed_on_storage_error(mock_download) -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    kwargs, session, task_repo, doc_repo, storage, publisher = _make_deps(task, doc)

    mock_download.return_value = b"PDF_CONTENT"
    storage.store.side_effect = OSError("disk full")

    msg = _make_message(task.id, doc.id)
    await process_download(msg, **kwargs)

    publisher.publish.assert_not_called()

    status_calls = task_repo.update_status.call_args_list
    assert status_calls[-1][0][2].status == "failed"
    assert "disk full" in status_calls[-1][0][2].error_message

    session.rollback.assert_called_once()


@respx.mock
@patch("worker_download.service.time.sleep")
async def test_download_retries_on_5xx(mock_sleep) -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    kwargs, _session, task_repo, _doc_repo, storage, publisher = _make_deps(
        task,
        doc,
        storage_uri=f"gs://bucket/documents/{doc.id}/original.pdf",
        max_retries=2,
    )

    call_count = [0]

    def make_response(request):
        call_count[0] += 1
        if call_count[0] == 1:
            return httpx.Response(500)
        return httpx.Response(200, content=b"PDF_RETRY_OK")

    respx.get(doc.source_url).mock(side_effect=make_response)

    msg = _make_message(task.id, doc.id)
    await process_download(msg, **kwargs)

    assert call_count[0] == 2

    status_calls = task_repo.update_status.call_args_list
    assert status_calls[-1][0][2].status == "completed"

    storage.store.assert_called_once()
    publisher.publish.assert_called_once()

    mock_sleep.assert_called()


@respx.mock
async def test_download_follows_redirect_to_pdf() -> None:
    """The crawler stores default.aspx?id=... URLs, which 302 to the real PDF path.

    httpx does not follow redirects by default, and raise_for_status() rejects an
    unfollowed redirect -- so without follow_redirects every download fails on a 302.
    """
    doc = _make_doc_read(source_url="https://example.com/default.aspx?id=2953158&ptid=")
    task = _make_task_read(doc.id)
    kwargs, _session, task_repo, _doc_repo, storage, publisher = _make_deps(
        task, doc, storage_uri=f"gs://bucket/documents/{doc.id}/original.pdf"
    )

    final_url = "https://example.com/filer/1374643/Beslut%202025-21.pdf"
    respx.get(doc.source_url).mock(
        return_value=httpx.Response(302, headers={"Location": final_url})
    )
    respx.get(final_url).mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.6 real bytes",
            headers={"content-type": "application/pdf"},
        )
    )

    await process_download(_make_message(task.id, doc.id), **kwargs)

    assert storage.store.call_args[0][1] == b"%PDF-1.6 real bytes"
    assert task_repo.update_status.call_args_list[-1][0][2].status == "completed"
    publisher.publish.assert_called_once()


@respx.mock
async def test_download_rejects_non_pdf_content_type() -> None:
    """A CMS error page still returns 200; status alone does not prove it is a PDF."""
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    kwargs, _session, task_repo, _doc_repo, storage, publisher = _make_deps(task, doc)

    respx.get(doc.source_url).mock(
        return_value=httpx.Response(
            200,
            content=b"<html>not found</html>",
            headers={"content-type": "text/html"},
        )
    )

    await process_download(_make_message(task.id, doc.id), **kwargs)

    storage.store.assert_not_called()
    publisher.publish.assert_not_called()
    assert task_repo.update_status.call_args_list[-1][0][2].status == "failed"
