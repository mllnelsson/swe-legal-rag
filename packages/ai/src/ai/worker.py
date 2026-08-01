"""The per-message trace scope pipeline workers hand to `shared.worker`.

Lives here rather than in `shared` because it needs llm-core's `trace_context`,
and `shared` must not depend on llm-core — the same reason `ai._observability`
is here. See [Observability](/observability.md) for the wiring invariant.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from llm_core import trace_context
from shared.queue.base import QueueMessage
from shared.worker import MessageScope

__all__ = ["worker_trace_scope"]


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
