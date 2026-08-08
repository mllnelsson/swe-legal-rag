from __future__ import annotations

import logging

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from ai import (
    close_llm_clients,
    create_embedding_ruler,
    get_embedding_prefixes,
    install_file_tracing,
    verify_embedding_window,
    worker_trace_scope,
)
from ai.providers.roles import LLMRole, create_llm_provider
from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.queue import create_queue_publisher
from shared.queue.base import QueueMessage, QueueSubscriber
from shared.repositories import chunk, document, task
from shared.worker import serve, subscribe_step
from worker_chunk.budget import compute_chunk_budget, fixed_overhead_tokens
from worker_chunk.chunker import CONTEXTUAL_SEPARATOR
from worker_chunk.config import get_chunk_settings
from worker_chunk.service import process_chunking

logger = logging.getLogger(__name__)

NAME = "worker-chunk"


def subscribe() -> QueueSubscriber:
    load_dotenv()
    settings = get_settings()
    chunk_settings = get_chunk_settings()

    install_file_tracing()
    llm_provider = create_llm_provider(LLMRole.SUMMARIZE)

    # Fail before consuming the queue rather than once per document, and warm the
    # tokenizer so the first message is not charged for loading it. The window is
    # what the tokenizer reports, so the budget below is derived from an observed
    # value rather than a declared one.
    ruler = create_embedding_ruler()
    _, passage_prefix = get_embedding_prefixes()
    prefix_tokens = ruler.count_tokens(passage_prefix)
    separator_tokens = ruler.count_tokens(CONTEXTUAL_SEPARATOR)
    window = verify_embedding_window(
        ruler,
        reserved_tokens=fixed_overhead_tokens(
            prefix_tokens=prefix_tokens, separator_tokens=separator_tokens
        ),
    )
    budget = compute_chunk_budget(
        window_tokens=window,
        prefix_tokens=prefix_tokens,
        separator_tokens=separator_tokens,
    )
    logger.info(
        "Chunk budget: window=%d reserve=%d chunk=%d overlap=%d",
        window,
        budget.summary_reserve_tokens,
        budget.max_tokens,
        budget.overlap_tokens,
    )

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
            count_tokens=ruler.count_tokens,
            budget=budget,
            next_topic=chunk_settings.chunk_next_topic,
            llm_provider=llm_provider,
        )

    return subscribe_step(
        topic=chunk_settings.chunk_topic,
        queue_settings=settings.queue,
        handle=handle,
        scope=worker_trace_scope(NAME),
        teardown=close_llm_clients,
    )


def main() -> None:
    configure_logging()
    serve(subscribe(), name=NAME)


if __name__ == "__main__":
    main()
