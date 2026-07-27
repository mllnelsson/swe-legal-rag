"""Writes LLM traces to file storage.

This is the concrete recorder behind llm-core's `TraceRecorder` hook. It lives
here rather than in `shared` because it needs both llm-core's record type and
`shared`'s storage layer, and `shared` must not depend on llm-core.

Records are handed to a background thread rather than written inline. A trace
write must never sit in front of an LLM call: on the chat path a synchronous
object-store round-trip would show up directly as first-token latency. The
trade is a bounded loss window — on SIGKILL or a hard crash, whatever is still
queued is lost. That is acceptable for cost telemetry, which is recomputable
from the provider's own dashboard, and `flush()` exists for the cases that need
certainty.

See [Observability](/observability.md) for the record schema and the wiring
invariant every process must follow.
"""

from __future__ import annotations

import atexit
import logging
import queue
import threading
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from llm_core import LLMCallRecord, Message, set_trace_recorder
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared.config import StorageSettings
from shared.storage import StorageBackend, create_storage_backend

from ai._pricing import estimate_cost_usd

logger = logging.getLogger(__name__)

# Bumped only when a field changes meaning or disappears. Adding a field does
# not break a reader and does not bump this.
TRACE_SCHEMA_VERSION = 1

# Streams roll over daily. It keeps any single object or file to a size worth
# opening, and makes "what did today cost" a single-key read.
_STREAM_KEY_DATE_FORMAT = "%Y-%m-%d"

# Sentinel telling the writer thread to stop.
_SHUTDOWN = object()


class LLMTraceConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    enabled: bool = Field(default=True, alias="LLM_TRACE_ENABLED")
    key_prefix: str = Field(default="llm-traces", alias="LLM_TRACE_KEY_PREFIX")
    queue_size: int = Field(default=1000, alias="LLM_TRACE_QUEUE_SIZE")
    flush_timeout_seconds: float = Field(default=5.0, alias="LLM_TRACE_FLUSH_TIMEOUT")


def _serialize_message(message: Message) -> dict[str, Any]:
    return {
        "role": str(message.role),
        "content": message.content,
        "tool_calls": [asdict(tc) for tc in message.tool_calls],
        "tool_call_id": message.tool_call_id,
        "tool_name": message.tool_name,
    }


def _serialize_cost(cost: Decimal | None) -> str | None:
    """Cost is a string, never a float.

    Floats do not round-trip a Decimal, and summing thousands of them drifts.
    A string reparses exactly.
    """
    return None if cost is None else str(cost)


def serialize_record(record: LLMCallRecord) -> dict[str, Any]:
    """Map a trace onto the JSON contract that analysis tools read.

    Prompts and responses are stored whole — never truncated, never redacted.
    Reading back exactly what was sent is the entire point.
    """
    cost = estimate_cost_usd(record.model, record.usage)
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "id": uuid.uuid4().hex,
        "started_at": _format_timestamp(record.started_at),
        "latency_ms": record.latency_ms,
        "operation": str(record.operation),
        "provider": record.provider,
        "model": record.model,
        "success": record.success,
        "error": None
        if record.success
        else {"type": record.error_type, "message": record.error_message},
        "messages": [_serialize_message(m) for m in record.messages],
        "response_text": record.response_text,
        "response_tool_calls": [asdict(tc) for tc in record.response_tool_calls],
        "usage": None if record.usage is None else asdict(record.usage),
        "estimated_cost_usd": _serialize_cost(cost),
        "context": dict(record.context),
    }


def _format_timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


class FileTraceRecorder:
    """Queues records and writes them from one background thread."""

    def __init__(self, storage: StorageBackend, config: LLMTraceConfig) -> None:
        self._storage = storage
        self._config = config
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=config.queue_size)
        self._dropped = 0
        # Daemon: a wedged object-store upload must not keep the process alive.
        self._writer = threading.Thread(
            target=self._drain, name="llm-trace-writer", daemon=True
        )
        self._writer.start()

    def record(self, record: LLMCallRecord) -> None:
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            # Shedding load beats blocking an LLM call behind a slow writer.
            self._dropped += 1
            logger.warning(
                "LLM trace queue full; dropped %d record(s) so far", self._dropped
            )

    def flush(self, timeout: float | None = None) -> bool:
        """Wait for queued records to be written. True if the queue drained."""
        deadline = (
            timeout if timeout is not None else self._config.flush_timeout_seconds
        )
        waiter = threading.Thread(target=self._queue.join, daemon=True)
        waiter.start()
        waiter.join(deadline)
        return not waiter.is_alive()

    def close(self) -> None:
        self._queue.put(_SHUTDOWN)
        self._writer.join(self._config.flush_timeout_seconds)

    def _drain(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SHUTDOWN:
                    return
                self._write(item)
            except Exception:
                # A failed trace write is never allowed to kill the writer;
                # the next record must still have somewhere to go.
                logger.exception("Failed to write LLM trace")
            finally:
                self._queue.task_done()

    def _write(self, record: LLMCallRecord) -> None:
        self._storage.add_json(self._stream_key(record), serialize_record(record))

    def _stream_key(self, record: LLMCallRecord) -> str:
        day = record.started_at.astimezone(UTC).strftime(_STREAM_KEY_DATE_FORMAT)
        return f"{self._config.key_prefix}/{day}"


def install_file_tracing(
    storage: StorageBackend | None = None,
    config: LLMTraceConfig | None = None,
) -> FileTraceRecorder | None:
    """Install the file recorder for this process. Never raises.

    Call once at startup, before any LLM call. Failing to install leaves no
    recorder at all, which llm-core handles as "tracing off" — observability
    must never be able to stop a worker or the API from starting.
    """
    config = config or LLMTraceConfig()
    if not config.enabled:
        logger.info("LLM tracing disabled (LLM_TRACE_ENABLED=false)")
        return None

    try:
        backend = storage or create_storage_backend(StorageSettings())
        recorder = FileTraceRecorder(backend, config)
    except Exception:
        logger.exception("Could not install LLM file tracing; continuing untraced")
        return None

    set_trace_recorder(recorder)
    atexit.register(_shutdown, recorder)
    logger.info("LLM tracing to storage key prefix %r", config.key_prefix)
    return recorder


def _shutdown(recorder: FileTraceRecorder) -> None:
    recorder.flush()
    recorder.close()
