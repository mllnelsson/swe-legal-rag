"""Writes LLM traces to local files, one file per billed call.

This is the concrete recorder behind llm-core's `TraceRecorder` hook. It lives
here rather than in `shared` because it needs llm-core's record type, and
`shared` must not depend on llm-core.

The layout carries the correlation, so nothing has to index it afterwards:

    {LOCAL_STORAGE_PATH}/llm-traces/{date}/{interaction_id}/{time}-{source}-{id}.json

One directory per unit of work — a chat turn, a worker message, a script case —
means "what did this request cost" is a sum over one folder, and `ls` shows the
shape of a turn at a glance. A record that arrives with no `interaction_id`
lands under `_unscoped`, which makes a gap in the wiring visible on disk rather
than leaving it a rule in a document.

Writes are synchronous, whole-file, and land via a temporary name plus
`os.replace`, so a reader never sees a partial file and two concurrent writers
never contend — they are always writing different paths. This puts a file write
in front of the next LLM call, which on local disk is tens of microseconds and
not worth hiding behind a thread. Over a network filesystem or an object store
it would be, and that is the condition under which buffering should come back.

See [Observability](/observability.md) for the record schema and the wiring
invariant every process must follow.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_core import (
    LLMCallRecord,
    Message,
    get_trace_recorder,
    set_trace_recorder,
)
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared.config import StorageSettings

logger = logging.getLogger(__name__)

# Bumped only when a field changes meaning or disappears. Adding a field does
# not break a reader and does not bump this.
TRACE_SCHEMA_VERSION = 1

# Directories roll over daily, so a day's spend is one prefix.
_DATE_FORMAT = "%Y-%m-%d"

# Time-of-day first, so a plain `ls` lists a request's calls in the order they
# were made.
_TIME_FORMAT = "%H%M%S.%f"

# Enough of the record's own id to keep two calls in the same microsecond apart.
# Timestamps alone would do while calls are sequential; this survives parallel
# tool calls without anything else having to change.
_ID_SUFFIX_LENGTH = 8

_FILE_SUFFIX = ".json"
_TEMP_SUFFIX = ".tmp"

# Where records with no interaction land. Named rather than dropped: a growing
# directory here is a wiring bug reporting itself.
_UNSCOPED = "_unscoped"
_UNKNOWN_SOURCE = "unknown"

# Path components are built from a client-suppliable id and a caller-set source,
# so they are whitelisted rather than trusted. Anything else becomes "_".
_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_MAX_COMPONENT_LENGTH = 128

# UTF-8 without escaping: every prompt in this project is Swedish, and
# \uXXXX-escaping them triples the size of a trace file for no benefit.
_JSON_ENSURE_ASCII = False

# Indented: these are read by a human with `cat` as often as by a tool.
_JSON_INDENT = 2


class LLMTraceConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    enabled: bool = Field(default=True, alias="LLM_TRACE_ENABLED")
    directory_name: str = Field(default="llm-traces", alias="LLM_TRACE_KEY_PREFIX")


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
        indent=_JSON_INDENT,
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


def _safe_component(value: str, *, fallback: str) -> str:
    """One path segment, built from a value this module does not control."""
    cleaned = _UNSAFE_PATH_CHARS.sub("_", value)[:_MAX_COMPONENT_LENGTH]
    # A component of dots would still traverse once the separators are gone.
    return cleaned if cleaned.strip(".") else fallback


def relative_path_for(payload: Mapping[str, Any], started_at: datetime) -> Path:
    """Where one serialized record belongs, relative to the trace root.

    Takes the serialized payload rather than the record so the filename can
    carry the record's own `id`, which is the thing already guaranteed unique.
    """
    context = payload.get("context") or {}
    moment = started_at.astimezone(UTC)

    interaction = _safe_component(
        str(context.get("interaction_id") or _UNSCOPED), fallback=_UNSCOPED
    )
    source = _safe_component(
        str(context.get("source") or _UNKNOWN_SOURCE), fallback=_UNKNOWN_SOURCE
    )
    identifier = str(payload.get("id", ""))[:_ID_SUFFIX_LENGTH]
    name = f"{moment.strftime(_TIME_FORMAT)}-{source}-{identifier}{_FILE_SUFFIX}"

    return Path(moment.strftime(_DATE_FORMAT)) / interaction / name


class FileTraceRecorder:
    """Writes each record as its own file under the trace root."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def record(self, record: LLMCallRecord) -> None:
        """Write one call, whole.

        Never raises: `TraceRecorder` forbids it, and observability failing must
        never turn into an application failure. A record that cannot be
        serialized is logged and dropped rather than costing the call it
        describes.
        """
        try:
            payload = serialize_record(record)
            path = self._root / relative_path_for(payload, record.started_at)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Written under a temporary name and moved into place, so a reader
            # running concurrently sees the file only once it is complete.
            temporary = path.with_name(path.name + _TEMP_SUFFIX)
            temporary.write_bytes(_dumps_record(payload))
            temporary.replace(path)
        except Exception:
            logger.warning("Failed to write LLM trace", exc_info=True)


def install_file_tracing(
    root: Path | None = None, config: LLMTraceConfig | None = None
) -> FileTraceRecorder | None:
    """Install the recorder for this process. Idempotent, and never raises.

    Every process making LLM calls calls this once at startup. Returning the
    already-installed recorder rather than replacing it keeps a second call
    harmless, which is what lets `scripts/run_pipeline.py` compose several
    worker `main()`s in one process.

    Returns None when tracing is disabled or the root cannot be created —
    observability must never stop a worker or the API from starting.
    """
    existing = get_trace_recorder()
    if isinstance(existing, FileTraceRecorder):
        return existing

    try:
        settings = config or LLMTraceConfig()
        if not settings.enabled:
            logger.info("LLM trace capture disabled")
            return None

        resolved = root or (
            StorageSettings().local_storage_path / settings.directory_name
        )
        resolved.mkdir(parents=True, exist_ok=True)
        recorder = FileTraceRecorder(resolved)
    except Exception:
        logger.warning("LLM trace capture unavailable", exc_info=True)
        return None

    set_trace_recorder(recorder)
    logger.info("LLM trace capture writing to %s", resolved)
    return recorder
