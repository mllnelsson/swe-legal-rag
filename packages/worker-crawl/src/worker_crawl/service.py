import logging

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate
from shared.dtos.task import TaskCreate
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from worker_crawl.client import CrawlClient

logger = logging.getLogger(__name__)


class CrawlResult(BaseModel):
    total_found: int
    new_documents: int
    skipped: int


class CrawlService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepo,
        task_repo: TaskRepo,
        queue_publisher: QueuePublisher,
        client: CrawlClient,
        source_url: str,
        topic: str = "download",
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._task_repo = task_repo
        self._queue_publisher = queue_publisher
        self._client = client
        self._source_url = source_url
        self._topic = topic

    async def run(self) -> CrawlResult:
        urls = self._client.fetch_pdf_urls(self._source_url)
        new_count = 0
        skip_count = 0

        for url in urls:
            try:
                existing = await self._document_repo.get_by_source_url(
                    self._session, url
                )
                if existing is not None:
                    skip_count += 1
                    continue

                try:
                    doc = await self._document_repo.create(
                        self._session, DocumentCreate(source_url=url)
                    )
                except IntegrityError:
                    await self._session.rollback()
                    skip_count += 1
                    continue

                await self._task_repo.create(
                    self._session,
                    TaskCreate(document_id=doc.id, step="crawl", status="completed"),
                )
                download_task = await self._task_repo.create(
                    self._session,
                    TaskCreate(document_id=doc.id, step="download", status="pending"),
                )
                # Commit before publishing so rows are visible to any separate session
                # (required when QUEUE_BACKEND=sync dispatches inline in the same process)
                await self._session.commit()
                self._queue_publisher.publish(
                    self._topic,
                    QueueMessage(task_id=download_task.id, document_id=doc.id),
                )
                new_count += 1
            except Exception:
                logger.warning("Failed to process URL %s", url, exc_info=True)
                await self._session.rollback()

        return CrawlResult(
            total_found=len(urls), new_documents=new_count, skipped=skip_count
        )
