"""Writes LLM traces to file storage.

This is the concrete recorder behind llm-core's `TraceRecorder` hook. It lives
here rather than in `shared` because it needs both llm-core's record type and
`shared`'s storage layer, and `shared` must not depend on llm-core.

The recorder owns the storage layout, not the storage backend. Records are
batched and written as whole JSONL objects through the plain `store()`
primitive. That keeps `StorageBackend` a blob store, and a local file and an
object store end up with byte-identical contents under the same key. Batching is
what makes the object-store path viable at all: embedding runs once per chunk
over the whole corpus, and one object per call would mean hundreds of thousands
of tiny billed writes.

Records are handed to a background thread rather than written inline. A trace
write must never sit in front of an LLM call: on the chat path a synchronous
object-store round-trip would show up directly as first-token latency. The trade
is a bounded loss window — on SIGKILL or a hard crash, whatever is still queued
or batched is lost. That is acceptable for cost telemetry, which is recomputable
from the provider's own dashboard, and `flush()` exists for the cases that need
certainty.

See [Observability](/observability.md) for the record schema and the wiring
invariant every process must follow.
"""

from __future__ import annotations

import atexit
import json
import logging
import queue
import threading
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from llm_core import LLMCallRecord, Message, set_trace_recorder
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared.config import StorageSettings
from shared.storage import StorageBackend, create_storage_backend

logger = logging.getLogger(__name__)

# Bumped only when a field changes meaning or disappears. Adding a field does
# not break a reader and does not bump this.
TRACE_SCHEMA_VERSION = 1

# Streams roll over daily. It keeps any single day's output worth opening, and
# makes "what did today cost" a single-prefix read.
_STREAM_KEY_DATE_FORMAT = "%Y-%m-%d"

# One object per flushed batch. The microsecond timestamp makes lexicographic
# key order approximate write order; the random suffix keeps keys unique when
# two processes flush in the same microsecond.
_BATCH_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%f"
_BATCH_SUFFIX_LENGTH = 8
_BATCH_FILE_SUFFIX = ".jsonl"

# UTF-8 without escaping: every prompt in this project is Swedish, and
# \uXXXX-escaping them triples the size of a trace object for no benefit.
_JSON_ENSURE_ASCII = False

# Compact separators — these are machine-read streams, not documents.
_JSON_SEPARATORS = (",", ":")

# Sentinels for the writer thread: write the open batch now, and stop.
_FLUSH = object()
_SHUTDOWN = object()


class LLMTraceConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    enabled: bool = Field(default=True, alias="LLM_TRACE_ENABLED")
    key_prefix: str = Field(default="llm-traces", alias="LLM_TRACE_KEY_PREFIX")
    queue_size: int = Field(default=1000, alias="LLM_TRACE_QUEUE_SIZE")
    flush_timeout_seconds: float = Field(default=5.0, alias="LLM_TRACE_FLUSH_TIMEOUT")
    batch_max_records: int = Field(default=100, alias="LLM_TRACE_BATCH_SIZE")
    batch_max_seconds: float = Field(default=5.0, alias="LLM_TRACE_BATCH_SECONDS")


def _coerce_unserializable(value: object) -> str:
    """Last-resort encoder for values `json` cannot represent.

    A trace record carries a caller-supplied context mapping whose values are
    opaque here. Coercing an odd value to its string form is always better than
    dropping the whole record.
    """
    return str(value)


def _dumps_record(record: Mapping[str, Any]) -> bytes:
    return json.dumps(
        record,
        ensure_ascii=_JSON_ENSURE_ASCII,
        separators=_JSON_SEPARATORS,
        default=_coerce_unserializable,
    ).encode("utf-8")


def _serialize_message(message: Message) -> dict[str, Any]:
    return {
        "role": str(message.role),
        "content": message.content,
        "tool_calls": [asdict(tc) for tc in message.tool_calls],
        "tool_call_id": message.tool_call_id,
        "tool_name": message.tool_name,
    }


def serialize_record(record: LLMCallRecord) -> dict[str, Any]:
    """Map a trace onto the JSON contract that analysis tools read.

    Prompts and responses are stored whole — never truncated, never redacted.
    Reading back exactly what was sent is the entire point.

    Cost is deliberately absent, and no rate table lives in this repo. `model`
    and `usage` are the complete raw material; applying a price to them is an
    analysis question, answered against
    [LLM pricing](/reference/llm-pricing.md) with whatever tool the analysis
    uses. Writing a number in would only freeze a rate that may be wrong or
    missing, for no gain.
    """
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
        "context": dict(record.context),
    }


def _format_timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _day_of(record: LLMCallRecord) -> str:
    return record.started_at.astimezone(UTC).strftime(_STREAM_KEY_DATE_FORMAT)


def _group_by_day(
    records: Sequence[LLMCallRecord],
) -> dict[str, list[LLMCallRecord]]:
    """A batch can straddle midnight; each day gets its own object."""
    grouped: dict[str, list[LLMCallRecord]] = defaultdict(list)
    for record in records:
        grouped[_day_of(record)].append(record)
    return grouped


def serialize_batch(records: Sequence[LLMCallRecord]) -> bytes:
    """One JSONL payload. A record that will not serialize is skipped, not fatal."""
    lines: list[bytes] = []
    for record in records:
        try:
            lines.append(_dumps_record(serialize_record(record)))
        except Exception:
            logger.exception("Skipping an LLM trace that could not be serialized")
    return b"".join(line + b"\n" for line in lines)


def _batch_object_name() -> str:
    timestamp = datetime.now(UTC).strftime(_BATCH_TIMESTAMP_FORMAT)
    suffix = uuid.uuid4().hex[:_BATCH_SUFFIX_LENGTH]
    return f"{timestamp}Z-{suffix}{_BATCH_FILE_SUFFIX}"


class FileTraceRecorder:
    """Batches records and writes them from one background thread."""

    def __init__(self, storage: StorageBackend, config: LLMTraceConfig) -> None:
        self._storage = storage
        self._config = config
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=config.queue_size)
        self._dropped = 0
        # Counts records accepted but not yet written. `flush()` waits on this
        # rather than on `Queue.join()`, because with batching a record leaves
        # the queue well before it reaches storage.
        self._unwritten = 0
        self._written = threading.Condition()
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
            return
        with self._written:
            self._unwritten += 1

    def flush(self, timeout: float | None = None) -> bool:
        """Write the open batch now and wait for it. True if everything landed.

        Asking rather than waiting matters: without the sentinel a partial batch
        would sit until `batch_max_seconds` elapsed, which on shutdown is a delay
        for no reason. A full queue means the writer is already behind and about
        to flush anyway, so a dropped request is harmless.
        """
        deadline = (
            timeout if timeout is not None else self._config.flush_timeout_seconds
        )
        try:
            self._queue.put_nowait(_FLUSH)
        except queue.Full:
            pass
        with self._written:
            return self._written.wait_for(
                lambda: self._unwritten == 0, timeout=deadline
            )

    def close(self) -> None:
        self._queue.put(_SHUTDOWN)
        self._writer.join(self._config.flush_timeout_seconds)

    def _drain(self) -> None:
        batch: list[LLMCallRecord] = []
        deadline: float | None = None

        while True:
            timeout = None if deadline is None else max(0.0, deadline - monotonic())
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                # The batch has been open for batch_max_seconds; write it.
                batch, deadline = self._flush_batch(batch), None
                continue

            if item is _SHUTDOWN:
                self._flush_batch(batch)
                return

            if item is _FLUSH:
                batch, deadline = self._flush_batch(batch), None
                continue

            batch.append(item)
            if deadline is None:
                deadline = monotonic() + self._config.batch_max_seconds
            if len(batch) >= self._config.batch_max_records:
                batch, deadline = self._flush_batch(batch), None

    def _flush_batch(self, batch: list[LLMCallRecord]) -> list[LLMCallRecord]:
        """Write a batch and return a fresh empty one.

        The `_unwritten` count drops even when the write fails, so a permanently
        failing backend cannot leave `flush()` waiting forever.
        """
        if not batch:
            return []
        try:
            self._write_batch(batch)
        except Exception:
            # A failed write is never allowed to kill the writer; the next batch
            # must still have somewhere to go.
            logger.exception("Failed to write %d LLM trace(s)", len(batch))
        finally:
            with self._written:
                self._unwritten -= len(batch)
                self._written.notify_all()
        return []

    def _write_batch(self, batch: Sequence[LLMCallRecord]) -> None:
        for day, records in _group_by_day(batch).items():
            payload = serialize_batch(records)
            if payload:
                self._storage.store(self._batch_key(day), payload)

    def _batch_key(self, day: str) -> str:
        return f"{self._config.key_prefix}/{day}/{_batch_object_name()}"


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
