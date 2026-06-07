import asyncio
import logging
import signal

from dotenv import load_dotenv

from shared.config import get_settings
from shared.db import get_async_session
from shared.queue import create_queue_publisher, create_queue_subscriber
from shared.queue.base import QueueMessage
from shared.repositories import DocumentRepository, TaskRepository
from shared.storage import create_storage_backend
from worker_parse.config import get_parse_settings
from worker_parse.parser import parse_pdf_with_pypdfium2
from worker_parse.service import process_parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    settings = get_settings()
    parse_settings = get_parse_settings()

    storage = create_storage_backend(settings.storage)
    publisher = create_queue_publisher(settings.queue)
    subscriber = create_queue_subscriber(settings.queue)

    def handle_message(message: QueueMessage) -> None:
        async def _handle() -> None:
            async with get_async_session() as session:
                doc_repo = DocumentRepository(session)
                task_repo = TaskRepository(session)
                await process_parse(
                    document_id=message.document_id,
                    task_id=message.task_id,
                    storage=storage,
                    document_repo=doc_repo,
                    task_repo=task_repo,
                    queue_publisher=publisher,
                    parser=parse_pdf_with_pypdfium2,
                    session=session,
                    next_topic=parse_settings.parse_next_topic,
                )

        asyncio.run(_handle())

    subscriber.subscribe(parse_settings.parse_topic, handle_message)

    def shutdown_handler(_signum: int, _frame: object) -> None:
        logger.info("Shutdown signal received, stopping...")
        subscriber.shutdown()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info("Parse worker starting, subscribing to topic: %s", parse_settings.parse_topic)
    subscriber.start()


if __name__ == "__main__":
    main()
