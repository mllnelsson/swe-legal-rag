from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from llm_core import (
    LLMCallRecord,
    LLMOperation,
    Message,
    Role,
    ToolCall,
    Usage,
    get_trace_recorder,
    set_trace_recorder,
)
from shared.storage.local import LocalStorageBackend

from ai._observability import (
    TRACE_SCHEMA_VERSION,
    FileTraceRecorder,
    LLMTraceConfig,
    install_file_tracing,
    serialize_record,
)

RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

EXPECTED_FIELDS = {
    "schema_version",
    "id",
    "started_at",
    "latency_ms",
    "operation",
    "provider",
    "model",
    "success",
    "error",
    "messages",
    "response_text",
    "response_tool_calls",
    "usage",
    "estimated_cost_usd",
    "context",
}


class FakeStorage:
    """In-memory StorageBackend.

    Only the JSON stream methods are exercised; the blob methods exist to
    satisfy the Protocol and fail loudly if anything reaches for them.
    """

    def __init__(self) -> None:
        self.streams: dict[str, list[Mapping[str, Any]]] = {}

    def add_json(self, key: str, record: Mapping[str, Any]) -> str:
        self.streams.setdefault(key, []).append(record)
        return f"memory://{key}"

    def iter_json(self, prefix: str) -> Iterator[Mapping[str, Any]]:
        for key in sorted(self.streams):
            if key.startswith(prefix):
                yield from self.streams[key]

    def store(self, key: str, data: bytes) -> str:
        raise NotImplementedError

    def retrieve(self, key: str) -> bytes:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        raise NotImplementedError


class ExplodingStorage(FakeStorage):
    def add_json(self, key: str, record: Mapping[str, Any]) -> str:
        raise RuntimeError("storage is down")


def _make_record(**overrides: Any) -> LLMCallRecord:
    defaults: dict[str, Any] = {
        "operation": LLMOperation.generate,
        "started_at": datetime(2026, 7, 27, 10, 15, 33, 123456, tzinfo=UTC),
        "latency_ms": 812,
        "provider": "gemini",
        "model": "gemini-2.5-flash-lite",
        "messages": (Message(role=Role.user, content="Vad gäller?"),),
        "response_text": "Svar",
        "response_tool_calls": (),
        "usage": Usage(input_tokens=1200, output_tokens=350, total_tokens=1550),
        "success": True,
        "error_type": None,
        "error_message": None,
        "context": {"source": "ai.decompose_query", "interaction_id": "abc"},
    }
    return LLMCallRecord(**{**defaults, **overrides})


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def config() -> LLMTraceConfig:
    return LLMTraceConfig(enabled=True, key_prefix="llm-traces", queue_size=100)


@pytest.fixture
def recorder(storage, config) -> Iterator[FileTraceRecorder]:
    recorder = FileTraceRecorder(storage, config)
    yield recorder
    recorder.close()


class TestSerializeRecord:
    def test_top_level_fields_are_exactly_the_contract(self) -> None:
        assert set(serialize_record(_make_record())) == EXPECTED_FIELDS

    def test_schema_version_is_stamped(self) -> None:
        assert serialize_record(_make_record())["schema_version"] == (
            TRACE_SCHEMA_VERSION
        )

    def test_timestamp_is_rfc3339_utc(self) -> None:
        assert RFC3339_UTC.match(serialize_record(_make_record())["started_at"])

    def test_naive_local_times_are_normalised_to_utc(self) -> None:
        record = _make_record(started_at=datetime(2026, 7, 27, 10, 15, 33, tzinfo=UTC))
        assert serialize_record(record)["started_at"].endswith("Z")

    def test_messages_are_stored_whole(self) -> None:
        long_prompt = "Ö" * 50_000
        record = _make_record(
            messages=(
                Message(role=Role.system, content="Du är en jurist."),
                Message(role=Role.user, content=long_prompt),
            )
        )

        messages = serialize_record(record)["messages"]

        assert [m["role"] for m in messages] == ["system", "user"]
        assert messages[1]["content"] == long_prompt

    def test_tool_calls_are_serialized(self) -> None:
        call = ToolCall(id="tc-1", name="search", arguments={"q": "kyrka"})
        record = _make_record(response_tool_calls=(call,))

        assert serialize_record(record)["response_tool_calls"] == [
            {"id": "tc-1", "name": "search", "arguments": {"q": "kyrka"}}
        ]

    def test_cost_is_a_string_never_a_float(self) -> None:
        """Floats do not round-trip Decimal and drift when summed."""
        serialized = serialize_record(_make_record())
        assert serialized["estimated_cost_usd"] == "0.00026000"
        assert isinstance(serialized["estimated_cost_usd"], str)

    def test_unpriced_model_yields_null_cost_not_zero(self) -> None:
        record = _make_record(model="zai-org/GLM-5.2")
        assert serialize_record(record)["estimated_cost_usd"] is None

    def test_missing_usage_is_null_not_zero(self) -> None:
        serialized = serialize_record(_make_record(usage=None))
        assert serialized["usage"] is None
        assert serialized["estimated_cost_usd"] is None

    def test_successful_record_has_no_error(self) -> None:
        assert serialize_record(_make_record())["error"] is None

    def test_failure_carries_type_and_message(self) -> None:
        record = _make_record(
            success=False,
            error_type="ProviderError",
            error_message="upstream 503",
            response_text=None,
        )

        serialized = serialize_record(record)

        assert serialized["success"] is False
        assert serialized["error"] == {
            "type": "ProviderError",
            "message": "upstream 503",
        }
        assert serialized["response_text"] is None

    def test_context_passes_through_verbatim(self) -> None:
        serialized = serialize_record(_make_record())
        assert serialized["context"] == {
            "source": "ai.decompose_query",
            "interaction_id": "abc",
        }


class TestFileTraceRecorder:
    def test_record_is_written_to_a_daily_stream(self, recorder, storage) -> None:
        recorder.record(_make_record())
        assert recorder.flush()

        assert list(storage.streams) == ["llm-traces/2026-07-27"]
        (written,) = storage.streams["llm-traces/2026-07-27"]
        assert written["operation"] == "generate"
        assert written["response_text"] == "Svar"

    def test_records_split_across_days(self, recorder, storage) -> None:
        recorder.record(_make_record())
        recorder.record(
            _make_record(started_at=datetime(2026, 7, 28, 1, 0, tzinfo=UTC))
        )
        assert recorder.flush()

        assert sorted(storage.streams) == [
            "llm-traces/2026-07-27",
            "llm-traces/2026-07-28",
        ]

    def test_every_record_gets_a_distinct_id(self, recorder, storage) -> None:
        recorder.record(_make_record())
        recorder.record(_make_record())
        assert recorder.flush()

        written = storage.streams["llm-traces/2026-07-27"]
        assert written[0]["id"] != written[1]["id"]

    def test_storage_failure_does_not_propagate(self, config) -> None:
        recorder = FileTraceRecorder(ExplodingStorage(), config)
        try:
            recorder.record(_make_record())  # must not raise
            assert recorder.flush()
        finally:
            recorder.close()

    def test_full_queue_drops_instead_of_blocking(self, storage) -> None:
        """An LLM call must never wait on a slow trace writer."""
        recorder = FileTraceRecorder(
            storage, LLMTraceConfig(enabled=True, queue_size=1)
        )
        try:
            for _ in range(50):
                recorder.record(_make_record())  # must not block or raise
        finally:
            recorder.close()


class TestAgainstRealStorage:
    """The path the workers actually take, with no fake in the way."""

    def test_records_land_in_a_readable_jsonl_stream(self, tmp_path, config) -> None:
        storage = LocalStorageBackend(tmp_path)
        recorder = FileTraceRecorder(storage, config)
        try:
            recorder.record(_make_record())
            recorder.record(_make_record(model="zai-org/GLM-5.2"))
            assert recorder.flush()
        finally:
            recorder.close()

        assert (tmp_path / "llm-traces" / "2026-07-27.jsonl").is_file()

        written = list(storage.iter_json("llm-traces/"))
        assert len(written) == 2
        assert written[0]["estimated_cost_usd"] == "0.00026000"
        assert written[1]["estimated_cost_usd"] is None
        assert written[0]["messages"][0]["content"] == "Vad gäller?"


class TestInstallFileTracing:
    def test_disabled_installs_nothing(self, storage) -> None:
        set_trace_recorder(None)
        result = install_file_tracing(
            storage, LLMTraceConfig(enabled=False, key_prefix="llm-traces")
        )

        assert result is None
        assert get_trace_recorder() is None

    def test_enabled_installs_the_recorder(self, storage, config) -> None:
        set_trace_recorder(None)
        try:
            recorder = install_file_tracing(storage, config)
            assert recorder is not None
            assert get_trace_recorder() is recorder
        finally:
            set_trace_recorder(None)

    def test_unbuildable_backend_leaves_tracing_off_rather_than_failing(
        self, monkeypatch
    ) -> None:
        """Observability must never stop a process from starting."""
        set_trace_recorder(None)
        monkeypatch.setattr(
            "ai._observability.create_storage_backend",
            lambda settings: (_ for _ in ()).throw(RuntimeError("no bucket")),
        )

        result = install_file_tracing(config=LLMTraceConfig(enabled=True))

        assert result is None
        assert get_trace_recorder() is None

    def test_a_backend_that_fails_at_write_time_still_installs(self, config) -> None:
        """Writes fail silently in the background; the process is unaffected."""
        set_trace_recorder(None)
        try:
            recorder = install_file_tracing(ExplodingStorage(), config)
            assert recorder is not None
            recorder.record(_make_record())
            assert recorder.flush()
        finally:
            set_trace_recorder(None)
