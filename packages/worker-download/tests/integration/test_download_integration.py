from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.task import TaskCreate
from shared.models.document import Document
from shared.models.task import Task
from shared.queue.base import QueueMessage
from shared.queue.sync import SyncQueuePublisher
from shared.storage.local import LocalStorageBackend
from worker_download.service import DownloadService

_FAKE_PDF = b"%PDF-1.4 fake content"
_FAKE_URL = "https://example.com/test.pdf"


def _make_service(
    session: AsyncSession,
    document_repo,
    task_repo,
    storage: LocalStorageBackend,
    publisher: SyncQueuePublisher,
) -> DownloadService:
    return DownloadService(
        session=session,
        document_repo=document_repo,
        task_repo=task_repo,
        storage=storage,
        queue_publisher=publisher,
        timeout=5,
        max_retries=1,
        rate_limit_delay=0,
        next_topic="parse",
    )


@pytest.mark.integration
async def test_full_download_stores_pdf_and_updates_document(
    session: AsyncSession,
    document_repo,
    task_repo,
    local_storage: LocalStorageBackend,
    sync_publisher: SyncQueuePublisher,
    published_messages: list,
    tmp_path: Path,
) -> None:
    doc = await document_repo.create(session, DocumentCreate(source_url=_FAKE_URL))
    task = await task_repo.create(
        session, TaskCreate(document_id=doc.id, step="download", status="pending")
    )
    await session.commit()

    with respx.mock:
        respx.get(_FAKE_URL).mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        service = _make_service(
            session, document_repo, task_repo, local_storage, sync_publisher
        )
        await service.handle_message(QueueMessage(task_id=task.id, document_id=doc.id))

    expected_path = tmp_path / "documents" / str(doc.id) / "original.pdf"
    assert expected_path.exists()
    assert expected_path.read_bytes() == _FAKE_PDF

    doc_row = (
        await session.execute(select(Document).where(Document.id == doc.id))
    ).scalar_one()
    assert doc_row.gcs_uri is not None
    assert str(doc.id) in doc_row.gcs_uri

    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.status == "completed"

    parse_task = (
        await session.execute(
            select(Task).where(Task.document_id == doc.id, Task.step == "parse")
        )
    ).scalar_one()
    assert parse_task.status == "pending"

    assert len(published_messages) == 1
    assert published_messages[0].document_id == doc.id


@pytest.mark.integration
async def test_download_idempotent_rerun(
    session: AsyncSession,
    document_repo,
    task_repo,
    local_storage: LocalStorageBackend,
    sync_publisher: SyncQueuePublisher,
    published_messages: list,
) -> None:
    doc = await document_repo.create(session, DocumentCreate(source_url=_FAKE_URL))
    await document_repo.update(
        session, doc.id, DocumentUpdate(gcs_uri="/existing/path.pdf")
    )
    task = await task_repo.create(
        session, TaskCreate(document_id=doc.id, step="download", status="pending")
    )
    await session.commit()

    with patch("worker_download.service._download_pdf") as mock_download:
        service = _make_service(
            session, document_repo, task_repo, local_storage, sync_publisher
        )
        await service.handle_message(QueueMessage(task_id=task.id, document_id=doc.id))
        mock_download.assert_not_called()

    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.status == "completed"

    parse_tasks = (
        (
            await session.execute(
                select(Task).where(Task.document_id == doc.id, Task.step == "parse")
            )
        )
        .scalars()
        .all()
    )
    assert len(parse_tasks) == 1
    assert parse_tasks[0].status == "pending"

    assert len(published_messages) == 1
    assert published_messages[0].document_id == doc.id
