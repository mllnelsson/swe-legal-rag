"""The per-message trace scope pipeline workers hand to `shared.worker`.

Lives here rather than in `shared` because it needs llm-core's `trace_context`,
and `shared` must not depend on llm-core — the same reason `ai._observability`
is here. See [Observability](/observability.md) for the wiring invariant.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from llm_core import aclose_async_openai, trace_context
from shared.queue.base import QueueMessage
from shared.worker import MessageScope

__all__ = ["close_llm_clients", "worker_trace_scope"]


async def close_llm_clients() -> None:
    """The `shared.worker` teardown every LLM-calling worker passes.

    A provider's HTTP client pools connections against the loop that opened
    them, and a worker opens one loop per message. Releasing them here — while
    that loop still runs — is what stopped the ingest retrying nearly every
    call; see `llm_core._clients`.
    """
    await aclose_async_openai()


def worker_trace_scope(source: str) -> MessageScope:
    """Attribute every LLM call made while handling a message.

    `source` names the worker; inner calls that name themselves override it.
    The document id is what ties a worker's token spend back to the document
    that caused it.
    """

    @contextmanager
    def scope(message: QueueMessage) -> Iterator[None]:
        with trace_context(
            document_id=str(message.document_id),
            task_id=str(message.task_id),
            source=source,
        ):
            yield

    return scope
