from __future__ import annotations

import asyncio
import logging
import signal

from dotenv import load_dotenv

from shared.config import get_settings
from shared.db import get_async_session
from shared.queue import create_queue_publisher, create_queue_subscriber
from shared.queue.base import QueueMessage
from shared.repositories import (
    DocumentEntityRepository,
    DocumentReferenceRepository,
    DocumentRepository,
    EntityRepository,
    TaskRepository,
    UnresolvedReferenceRepository,
)
from worker_extract.config import get_extract_settings
from worker_extract.services.extraction_service import process_extraction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    settings = get_settings()
    extract_settings = get_extract_settings()

    publisher = create_queue_publisher(settings.queue)
    subscriber = create_queue_subscriber(settings.queue)

    def handle_message(message: QueueMessage) -> None:
        async def _handle() -> None:
            async with get_async_session() as session:
                await process_extraction(
                    document_id=message.document_id,
                    task_id=message.task_id,
                    document_repo=DocumentRepository(session),
                    task_repo=TaskRepository(session),
                    entity_repo=EntityRepository(session),
                    doc_entity_repo=DocumentEntityRepository(session),
                    ref_repo=DocumentReferenceRepository(session),
                    unresolved_repo=UnresolvedReferenceRepository(session),
                    queue_publisher=publisher,
                    session=session,
                    next_topic=extract_settings.extract_next_topic,
                )

        asyncio.run(_handle())

    subscriber.subscribe(extract_settings.extract_topic, handle_message)

    def shutdown_handler(_signum: int, _frame: object) -> None:
        logger.info("Shutdown signal received, stopping...")
        subscriber.shutdown()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info(
        "Extract worker starting, subscribing to topic: %s",
        extract_settings.extract_topic,
    )
    subscriber.start()


if __name__ == "__main__":
    main()
