import logging

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate
from shared.dtos.task import TaskCreate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from shared.source_headline import parse_source_headline
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

    # The URL and the document id both identify the *listing entry*. The listing
    # published 21/2021 twice, under ids 2265536 and 2266136 three days apart,
    # and neither key saw it: the corpus held the same decision twice, with its
    # own chunks, its own entity links and its own place in every search result.
    # The headline states the decision's own identity, so that is what decides.
    parsed_headline = parse_source_headline(listing.headline)
    if parsed_headline is not None:
        duplicate = await document_repo.get_by_source_decision_number(
            session, parsed_headline.decision_number
        )
        if duplicate is not None:
            logger.info(
                "Decision %s already crawled as document %s; skipping listing %d",
                parsed_headline.decision_number,
                duplicate.source_document_id,
                listing.document_id,
            )
            return False

    try:
        doc = await document_repo.create(
            session,
            DocumentCreate(
                source_url=url,
                source_document_id=listing.document_id,
                source_headline=listing.headline,
                source_decision_number=(
                    parsed_headline.decision_number if parsed_headline else None
                ),
                source_published_at=listing.published_at,
            ),
        )
    except IntegrityError:
        # Raced with another run, or the same decision reachable under a second
        # listing entry -- uq_documents_source_document_id and
        # uq_documents_source_decision_number are the backstops.
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
