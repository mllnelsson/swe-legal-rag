import logging

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate
from shared.dtos.task import TaskCreate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from worker_crawl._protocols import DecisionSource
from worker_crawl.odata import DecisionListing, ODataConfig
from worker_crawl.tags import parse_tag_index, select_tag_ids
from worker_crawl.years import YearSelection

logger = logging.getLogger(__name__)


class CrawlResult(BaseModel):
    total_found: int
    new_documents: int
    skipped: int
    years_crawled: tuple[int, ...] = ()
    tags_used: int = 0


async def process_crawl(
    *,
    session: AsyncSession,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    source: DecisionSource,
    odata_config: ODataConfig,
    selection: YearSelection,
    topic: PipelineStep,
) -> CrawlResult:
    tag_index = parse_tag_index(source.fetch_decision_tags(odata_config))
    tags = select_tag_ids(tag_index, selection)
    if tags.missing_years:
        logger.warning(
            "No decision tag exists for %s; those years were skipped.",
            ", ".join(str(year) for year in tags.missing_years),
        )

    listings = source.fetch_decisions(odata_config, tags.tag_ids)
    new_count = 0
    skip_count = 0

    for listing in listings:
        try:
            created = await _store_decision(
                session=session,
                document_repo=document_repo,
                task_repo=task_repo,
                queue_publisher=queue_publisher,
                source=source,
                odata_config=odata_config,
                listing=listing,
                topic=topic,
            )
            if created:
                new_count += 1
            else:
                skip_count += 1
        except Exception:
            logger.warning(
                "Failed to process decision %d", listing.document_id, exc_info=True
            )
            await session.rollback()

    return CrawlResult(
        total_found=len(listings),
        new_documents=new_count,
        skipped=skip_count,
        years_crawled=tags.matched_years,
        tags_used=len(tags.tag_ids),
    )


async def _store_decision(
    *,
    session: AsyncSession,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    source: DecisionSource,
    odata_config: ODataConfig,
    listing: DecisionListing,
    topic: PipelineStep,
) -> bool:
    """Persist one decision and queue its download. Returns False if already known."""
    url = source.decision_source_url(odata_config, listing.document_id)

    existing = await document_repo.get_by_source_url(session, url)
    if existing is not None:
        return False

    try:
        doc = await document_repo.create(
            session,
            DocumentCreate(
                source_url=url,
                source_document_id=listing.document_id,
                source_headline=listing.headline,
                source_published_at=listing.published_at,
            ),
        )
    except IntegrityError:
        # Raced with another run, or the same document reachable under a second URL --
        # the uq_documents_source_document_id constraint is the backstop.
        await session.rollback()
        return False

    await task_repo.create(
        session,
        TaskCreate(
            document_id=doc.id,
            step=PipelineStep.CRAWL,
            status=TaskStatus.COMPLETED,
        ),
    )
    download_task = await task_repo.create(
        session,
        TaskCreate(
            document_id=doc.id,
            step=PipelineStep.DOWNLOAD,
            status=TaskStatus.PENDING,
        ),
    )
    # Commit before publishing so rows are visible to any separate session
    # (required when QUEUE_BACKEND=sync dispatches inline in the same process)
    await session.commit()
    queue_publisher.publish(
        topic,
        QueueMessage(task_id=download_task.id, document_id=doc.id),
    )
    return True
