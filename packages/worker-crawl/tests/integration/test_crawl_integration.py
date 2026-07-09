from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.document import Document
from shared.models.task import Task
from shared.queue.sync import SyncQueuePublisher
from worker_crawl.service import CrawlResult, process_crawl

_FAKE_URLS = [
    "https://example.com/doc1.pdf",
    "https://example.com/doc2.pdf",
    "https://example.com/doc3.pdf",
]


def _make_kwargs(
    urls: list[str],
    session: AsyncSession,
    document_repo,
    task_repo,
    publisher: SyncQueuePublisher,
) -> dict:
    client = MagicMock()
    client.fetch_pdf_urls.return_value = urls
    return dict(
        session=session,
        document_repo=document_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        client=client,
        source_url="https://example.com/decisions",
        topic="download",
    )


@pytest.mark.integration
async def test_full_crawl_creates_documents_and_tasks(
    session: AsyncSession,
    document_repo,
    task_repo,
    sync_publisher: SyncQueuePublisher,
    published_messages: list,
) -> None:
    kwargs = _make_kwargs(_FAKE_URLS, session, document_repo, task_repo, sync_publisher)
    result = await process_crawl(**kwargs)

    assert result == CrawlResult(total_found=3, new_documents=3, skipped=0)
    assert len(published_messages) == 3

    docs = (await session.execute(select(Document))).scalars().all()
    assert len(docs) == 3
    assert {d.source_url for d in docs} == set(_FAKE_URLS)

    crawl_tasks = (
        (
            await session.execute(
                select(Task).where(Task.step == "crawl", Task.status == "completed")
            )
        )
        .scalars()
        .all()
    )
    assert len(crawl_tasks) == 3

    download_tasks = (
        (
            await session.execute(
                select(Task).where(Task.step == "download", Task.status == "pending")
            )
        )
        .scalars()
        .all()
    )
    assert len(download_tasks) == 3


@pytest.mark.integration
async def test_crawl_idempotent_rerun(
    session: AsyncSession,
    document_repo,
    task_repo,
    sync_publisher: SyncQueuePublisher,
    published_messages: list,
) -> None:
    kwargs = _make_kwargs(_FAKE_URLS, session, document_repo, task_repo, sync_publisher)

    first_result = await process_crawl(**kwargs)
    assert first_result == CrawlResult(total_found=3, new_documents=3, skipped=0)

    second_result = await process_crawl(**kwargs)
    assert second_result == CrawlResult(total_found=3, new_documents=0, skipped=3)

    docs = (await session.execute(select(Document))).scalars().all()
    assert len(docs) == 3
    # Second run should publish no new messages (only 3 from first run)
    assert len(published_messages) == 3
