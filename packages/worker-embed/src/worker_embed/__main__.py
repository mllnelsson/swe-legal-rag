from __future__ import annotations

import asyncio
import logging
import signal

from dotenv import load_dotenv

from ai import create_embedding_provider
from shared.config import get_settings
from shared.db import get_async_session
from shared.queue import create_queue_subscriber
from shared.queue.base import QueueMessage
from shared.repositories import chunk, task
from worker_embed.config import get_embed_settings
from worker_embed.service import process_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    settings = get_settings()
    embed_settings = get_embed_settings()

    embedding_provider = create_embedding_provider()
    subscriber = create_queue_subscriber(settings.queue)

    def handle_message(message: QueueMessage) -> None:
        async def _handle() -> None:
            async with get_async_session() as session:
                await process_embedding(
                    document_id=message.document_id,
                    task_id=message.task_id,
                    chunk_repo=chunk,
                    task_repo=task,
                    embedding_provider=embedding_provider,
                    session=session,
                )

        asyncio.run(_handle())

    subscriber.subscribe(embed_settings.embed_topic, handle_message)

    def shutdown_handler(_signum: int, _frame: object) -> None:
        logger.info("Shutdown signal received, stopping...")
        subscriber.shutdown()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info(
        "Embed worker starting, subscribing to topic: %s",
        embed_settings.embed_topic,
    )
    subscriber.start()


if __name__ == "__main__":
    main()
