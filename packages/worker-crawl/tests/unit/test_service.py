import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.dtos.document import DocumentRead
from shared.dtos.task import TaskRead
from shared.queue.base import QueueMessage
from worker_crawl.service import CrawlResult, CrawlService


def _make_doc_read(source_url: str) -> DocumentRead:
    now = datetime.now(tz=timezone.utc)
    return DocumentRead(
        id=uuid.uuid4(),
        source_url=source_url,
        gcs_uri=None,
        raw_text=None,
        summary=None,
        case_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=now,
        updated_at=now,
    )


def _make_task_read(document_id: uuid.UUID, step: str, status: str) -> TaskRead:
    return TaskRead(
        id=uuid.uuid4(),
        document_id=document_id,
        step=step,
        status=status,
        error_message=None,
        started_at=None,
        completed_at=None,
    )


def _make_service(
    urls: list[str],
    existing_urls: set[str] | None = None,
) -> tuple[CrawlService, MagicMock, MagicMock, MagicMock]:
    existing_urls = existing_urls or set()

    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    doc_repo = MagicMock()
    task_repo = MagicMock()
    publisher = MagicMock()
    client = MagicMock()

    client.fetch_pdf_urls.return_value = urls

    async def get_by_source_url(url: str) -> DocumentRead | None:
        if url in existing_urls:
            return _make_doc_read(url)
        return None

    doc_repo.get_by_source_url = get_by_source_url

    async def create_doc(dto):
        return _make_doc_read(dto.source_url)

    doc_repo.create = create_doc

    async def create_task(dto):
        return _make_task_read(dto.document_id, dto.step, dto.status)

    task_repo.create = create_task

    service = CrawlService(
        session=session,
        document_repo=doc_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        client=client,
        source_url="https://example.com/decisions",
        topic="download",
    )
    return service, session, publisher, client


@pytest.mark.asyncio
async def test_run_creates_documents_for_new_urls() -> None:
    service, session, publisher, _ = _make_service(
        urls=["https://example.com/a.pdf", "https://example.com/b.pdf"]
    )

    result = await service.run()

    assert result == CrawlResult(total_found=2, new_documents=2, skipped=0)
    assert publisher.publish.call_count == 2
    assert session.commit.call_count == 2


@pytest.mark.asyncio
async def test_run_skips_existing_documents() -> None:
    service, session, publisher, _ = _make_service(
        urls=["https://example.com/a.pdf", "https://example.com/b.pdf"],
        existing_urls={"https://example.com/a.pdf"},
    )

    result = await service.run()

    assert result == CrawlResult(total_found=2, new_documents=1, skipped=1)
    assert publisher.publish.call_count == 1


@pytest.mark.asyncio
async def test_run_returns_empty_result_for_no_urls() -> None:
    service, session, publisher, _ = _make_service(urls=[])

    result = await service.run()

    assert result == CrawlResult(total_found=0, new_documents=0, skipped=0)
    publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_run_publishes_correct_message() -> None:
    service, _, publisher, _ = _make_service(
        urls=["https://example.com/doc.pdf"]
    )

    await service.run()

    assert publisher.publish.call_count == 1
    topic, message = publisher.publish.call_args[0]
    assert topic == "download"
    assert isinstance(message, QueueMessage)
    assert message.document_id is not None
    assert message.task_id is not None


@pytest.mark.asyncio
async def test_run_commits_before_publish() -> None:
    committed_before_publish = []
    commit_count = [0]

    session = MagicMock()

    async def track_commit():
        commit_count[0] += 1

    session.commit = track_commit
    session.rollback = AsyncMock()

    def track_publish(topic, message):
        committed_before_publish.append(commit_count[0])

    doc_repo = MagicMock()
    task_repo = MagicMock()
    publisher = MagicMock()
    publisher.publish.side_effect = track_publish
    client = MagicMock()
    client.fetch_pdf_urls.return_value = ["https://example.com/doc.pdf"]
    doc_repo.get_by_source_url = AsyncMock(return_value=None)
    doc_repo.create = AsyncMock(return_value=_make_doc_read("https://example.com/doc.pdf"))
    task_repo.create = AsyncMock(side_effect=lambda dto: _make_task_read(dto.document_id, dto.step, dto.status))

    service = CrawlService(
        session=session,
        document_repo=doc_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        client=client,
        source_url="https://example.com/decisions",
        topic="download",
    )
    await service.run()

    assert committed_before_publish == [1], "commit must happen before publish"


@pytest.mark.asyncio
async def test_run_continues_after_per_url_failure() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    doc_repo = MagicMock()
    task_repo = MagicMock()
    publisher = MagicMock()
    client = MagicMock()

    client.fetch_pdf_urls.return_value = [
        "https://example.com/fail.pdf",
        "https://example.com/ok.pdf",
    ]

    call_count = [0]

    async def get_by_source_url(url: str) -> None:
        return None

    async def create_doc(dto):
        call_count[0] += 1
        if "fail" in dto.source_url:
            raise RuntimeError("network failure")
        return _make_doc_read(dto.source_url)

    async def create_task(dto):
        return _make_task_read(dto.document_id, dto.step, dto.status)

    doc_repo.get_by_source_url = get_by_source_url
    doc_repo.create = create_doc
    task_repo.create = create_task

    service = CrawlService(
        session=session,
        document_repo=doc_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        client=client,
        source_url="https://example.com/decisions",
        topic="download",
    )

    result = await service.run()

    assert result.total_found == 2
    assert result.new_documents == 1
    assert publisher.publish.call_count == 1
