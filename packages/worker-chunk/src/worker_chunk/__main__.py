from __future__ import annotations

import logging

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from ai import install_file_tracing, worker_trace_scope
from ai.providers.roles import LLMRole, create_llm_provider
from shared.config import get_settings
from shared.queue import create_queue_publisher
from shared.queue.base import QueueMessage, QueueSubscriber
from shared.repositories import chunk, document, task
from shared.worker import serve, subscribe_step
from worker_chunk.config import get_chunk_settings
from worker_chunk.service import process_chunking

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NAME = "worker-chunk"


def subscribe() -> QueueSubscriber:
    load_dotenv()
    settings = get_settings()
    chunk_settings = get_chunk_settings()

    install_file_tracing()
    llm_provider = create_llm_provider(LLMRole.SUMMARIZE)

    publisher = create_queue_publisher(settings.queue)

    async def handle(message: QueueMessage, session: AsyncSession) -> None:
        await process_chunking(
            document_id=message.document_id,
            task_id=message.task_id,
            document_repo=document,
            chunk_repo=chunk,
            task_repo=task,
            queue_publisher=publisher,
            session=session,
            next_topic=chunk_settings.chunk_next_topic,
            llm_provider=llm_provider,
        )

    return subscribe_step(
        topic=chunk_settings.chunk_topic,
        queue_settings=settings.queue,
        handle=handle,
        scope=worker_trace_scope(NAME),
    )


def main() -> None:
    serve(subscribe(), name=NAME)


if __name__ == "__main__":
    main()
