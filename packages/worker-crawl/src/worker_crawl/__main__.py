import asyncio
import logging

from dotenv import load_dotenv

from shared.config import get_settings
from shared.db import get_async_session
from shared.queue import create_queue_publisher
from shared.repositories import DocumentRepository, TaskRepository
from worker_crawl.client import CrawlClient
from worker_crawl.config import get_crawl_settings
from worker_crawl.service import CrawlService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _run() -> None:
    settings = get_settings()
    crawl_settings = get_crawl_settings()

    publisher = create_queue_publisher(settings.queue)
    client = CrawlClient(timeout=crawl_settings.crawl_request_timeout)

    async with get_async_session() as session:
        doc_repo = DocumentRepository(session)
        task_repo = TaskRepository(session)
        service = CrawlService(
            session=session,
            document_repo=doc_repo,
            task_repo=task_repo,
            queue_publisher=publisher,
            client=client,
            source_url=crawl_settings.crawl_source_url,
            topic=crawl_settings.crawl_topic,
        )
        result = await service.run()

    logger.info(
        "Crawl complete: found=%d new=%d skipped=%d",
        result.total_found,
        result.new_documents,
        result.skipped,
    )


def main() -> None:
    load_dotenv()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
