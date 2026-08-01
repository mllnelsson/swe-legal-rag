from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from ai import (
    create_embedding_provider,
    get_embedding_prefixes,
    install_file_tracing,
    verify_embedding_dimension,
    worker_trace_scope,
)
from shared.config import get_settings
from shared.queue.base import QueueMessage, QueueSubscriber
from shared.repositories import chunk, task
from shared.worker import serve, subscribe_step
from worker_embed.config import get_embed_settings
from worker_embed.service import process_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NAME = "worker-embed"


def subscribe() -> QueueSubscriber:
    load_dotenv()
    embed_settings = get_embed_settings()

    # Before the provider is built, so the dimension probe below — a real
    # billed embedding on a hosted provider — is recorded like any other call.
    install_file_tracing()
    embedding_provider = create_embedding_provider()
    _, passage_prefix = get_embedding_prefixes()

    # Fail before consuming the queue rather than once per document. Also warms
    # the model, so the first message is not charged for loading it.
    dimension = asyncio.run(verify_embedding_dimension(embedding_provider))
    logger.info("Embedding dimension verified: %d", dimension)

    async def handle(message: QueueMessage, session: AsyncSession) -> None:
        await process_embedding(
            document_id=message.document_id,
            task_id=message.task_id,
            chunk_repo=chunk,
            task_repo=task,
            embedding_provider=embedding_provider,
            session=session,
            passage_prefix=passage_prefix,
        )

    return subscribe_step(
        topic=embed_settings.embed_topic,
        queue_settings=get_settings().queue,
        handle=handle,
        scope=worker_trace_scope(NAME),
    )


def main() -> None:
    serve(subscribe(), name=NAME)


if __name__ == "__main__":
    main()
