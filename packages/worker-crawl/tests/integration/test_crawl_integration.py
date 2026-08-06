from datetime import datetime, timezone
from unittest.mock import MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import PipelineStep
from shared.models.document import Document
from shared.models.task import Task
from shared.queue.base import QueuePublisher
from worker_crawl.odata import DecisionListing, ODataConfig
from worker_crawl.service import process_crawl
from worker_crawl.tags import DecisionTag
from worker_crawl.years import YearSelection

DOCUMENT_URL_TEMPLATE = "https://example.com/default.aspx?id={document_id}&ptid="

ODATA_CONFIG = ODataConfig(
    base_url="https://example.com/odata/",
    api_key="test-key",
    web_id=1374643,
    document_url_template=DOCUMENT_URL_TEMPLATE,
    page_size=10,
    request_timeout=5,
    rate_limit_delay=0.0,
    max_retries=1,
)

TAGS = [DecisionTag(database_id=100104828, name="Överklagandenämndens beslut 2025")]

LISTINGS = [
    DecisionListing(
        document_id=document_id,
        headline=f"Beslut 2025-{index:02d}",
        published_at=datetime(2025, 3, index + 1, tzinfo=timezone.utc),
    )
    for index, document_id in enumerate([2953158, 2953155, 2953153], start=1)
]

EXPECTED_URLS = {
    DOCUMENT_URL_TEMPLATE.format(document_id=listing.document_id)
    for listing in LISTINGS
}


def _make_kwargs(
    session: AsyncSession,
    document_repo,
    task_repo,
    publisher: QueuePublisher,
) -> dict:
    source = MagicMock()
    source.fetch_decision_tags.return_value = TAGS
    source.fetch_decisions.return_value = LISTINGS
    source.decision_source_url = lambda _config, document_id: (
        DOCUMENT_URL_TEMPLATE.format(document_id=document_id)
    )
    return dict(
        session=session,
        document_repo=document_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        source=source,
        odata_config=ODATA_CONFIG,
        selection=YearSelection(years=(2025,)),
        topic=PipelineStep.DOWNLOAD,
    )


async def test_full_crawl_creates_documents_and_tasks(
    session: AsyncSession,
    document_repo,
    task_repo,
    sync_publisher: QueuePublisher,
    published_messages: list,
) -> None:
    result = await process_crawl(
        **_make_kwargs(session, document_repo, task_repo, sync_publisher)
    )

    assert (result.total_found, result.new_documents, result.skipped) == (3, 3, 0)
    assert result.years_crawled == (2025,)
    assert len(published_messages) == 3

    docs = (await session.execute(select(Document))).scalars().all()
    assert len(docs) == 3
    assert {doc.source_url for doc in docs} == EXPECTED_URLS

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


async def test_crawl_persists_listing_metadata(
    session: AsyncSession,
    document_repo,
    task_repo,
    sync_publisher: QueuePublisher,
) -> None:
    await process_crawl(
        **_make_kwargs(session, document_repo, task_repo, sync_publisher)
    )

    doc = (
        (
            await session.execute(
                select(Document).where(Document.source_document_id == 2953158)
            )
        )
        .scalars()
        .one()
    )
    assert doc.source_headline == "Beslut 2025-01"
    assert doc.source_published_at is not None
    assert doc.source_url == DOCUMENT_URL_TEMPLATE.format(document_id=2953158)


async def test_crawl_idempotent_rerun(
    session: AsyncSession,
    document_repo,
    task_repo,
    sync_publisher: QueuePublisher,
    published_messages: list,
) -> None:
    kwargs = _make_kwargs(session, document_repo, task_repo, sync_publisher)

    first = await process_crawl(**kwargs)
    assert (first.total_found, first.new_documents, first.skipped) == (3, 3, 0)

    second = await process_crawl(**kwargs)
    assert (second.total_found, second.new_documents, second.skipped) == (3, 0, 3)

    docs = (await session.execute(select(Document))).scalars().all()
    assert len(docs) == 3
    # The second run must publish nothing new (only the 3 from the first run).
    assert len(published_messages) == 3
