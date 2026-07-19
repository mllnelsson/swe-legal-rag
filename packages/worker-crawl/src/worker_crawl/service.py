import logging

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate
from shared.dtos.task import TaskCreate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from worker_crawl.client import CrawlClient

logger = logging.getLogger(__name__)


class CrawlResult(BaseModel):
    total_found: int
    new_documents: int
    skipped: int


async def process_crawl(
    *,
    session: AsyncSession,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    client: CrawlClient,
    source_url: str,
    topic: PipelineStep,
) -> CrawlResult:
    urls = client.fetch_pdf_urls(source_url)
    new_count = 0
    skip_count = 0

    for url in urls:
        try:
            existing = await document_repo.get_by_source_url(session, url)
            if existing is not None:
                skip_count += 1
                continue

            try:
                doc = await document_repo.create(
                    session, DocumentCreate(source_url=url)
                )
            except IntegrityError:
                await session.rollback()
                skip_count += 1
                continue

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
            new_count += 1
        except Exception:
            logger.warning("Failed to process URL %s", url, exc_info=True)
            await session.rollback()

    return CrawlResult(
        total_found=len(urls), new_documents=new_count, skipped=skip_count
    )
