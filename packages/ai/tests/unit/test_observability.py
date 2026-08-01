from __future__ import annotations

import json
import re
from collections.abc import Iterator
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

BATCH_KEY = re.compile(
    r"^llm-traces/\d{4}-\d{2}-\d{2}/\d{8}T\d{9,}Z-[0-9a-f]{8}\.jsonl$"
)

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
    "context",
}


class FakeStorage:
    """In-memory StorageBackend.

    Only `store` is exercised; the rest exist to satisfy the Protocol and fail
    loudly if anything reaches for them.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def store(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return f"memory://{key}"

    def records(self) -> list[dict[str, Any]]:
        """Every record written, across every object, in key order."""
        return [
            json.loads(line)
            for key in sorted(self.objects)
            for line in self.objects[key].splitlines()
            if line.strip()
        ]

    def keys_for_day(self, day: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(f"llm-traces/{day}/"))

    def retrieve(self, key: str) -> bytes:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        raise NotImplementedError


class ExplodingStorage(FakeStorage):
    def store(self, key: str, data: bytes) -> str:
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

    def test_cost_is_not_frozen_into_the_record(self) -> None:
        """Cost is priced at read time from `model` and `usage`."""
        serialized = serialize_record(_make_record())
        assert "estimated_cost_usd" not in serialized
        assert serialized["model"] == "gemini-2.5-flash-lite"
        assert serialized["usage"] == {
            "input_tokens": 1200,
            "output_tokens": 350,
            "total_tokens": 1550,
        }

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

    def test_missing_usage_is_null_not_zero(self) -> None:
        assert serialize_record(_make_record(usage=None))["usage"] is None

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
    def test_record_is_written_under_a_daily_batch_key(self, recorder, storage) -> None:
        recorder.record(_make_record())
        assert recorder.flush()

        (key,) = storage.objects
        assert BATCH_KEY.match(key)
        assert key.startswith("llm-traces/2026-07-27/")

        (written,) = storage.records()
        assert written["operation"] == "generate"
        assert written["response_text"] == "Svar"

    def test_a_batch_becomes_one_object_not_one_per_record(
        self, recorder, storage
    ) -> None:
        """The whole point: an object store must not get one write per call."""
        for _ in range(25):
            recorder.record(_make_record())
        assert recorder.flush()

        assert len(storage.objects) == 1
        assert len(storage.records()) == 25

    def test_batch_is_written_once_it_reaches_the_size_limit(self, storage) -> None:
        recorder = FileTraceRecorder(
            storage,
            LLMTraceConfig(enabled=True, batch_max_records=5, batch_max_seconds=30.0),
        )
        try:
            for _ in range(10):
                recorder.record(_make_record())
            assert recorder.flush()
        finally:
            recorder.close()

        # Two size-triggered batches, not one time-triggered one.
        assert len(storage.objects) == 2
        assert len(storage.records()) == 10

    def test_batch_is_written_once_the_time_limit_elapses(self, storage) -> None:
        """A trickle of calls must not sit unwritten waiting for a full batch."""
        recorder = FileTraceRecorder(
            storage,
            LLMTraceConfig(
                enabled=True, batch_max_records=1000, batch_max_seconds=0.05
            ),
        )
        try:
            recorder.record(_make_record())
            # No flush() — the elapsed-time path is what is under test.
            deadline = datetime.now(UTC).timestamp() + 5
            while not storage.objects and datetime.now(UTC).timestamp() < deadline:
                pass
        finally:
            recorder.close()

        assert len(storage.records()) == 1

    def test_close_writes_a_partial_batch(self, storage) -> None:
        recorder = FileTraceRecorder(
            storage,
            LLMTraceConfig(
                enabled=True, batch_max_records=1000, batch_max_seconds=30.0
            ),
        )
        recorder.record(_make_record())
        recorder.close()

        assert len(storage.records()) == 1

    def test_records_split_across_days(self, recorder, storage) -> None:
        """One batch straddling midnight becomes one object per day."""
        recorder.record(_make_record())
        recorder.record(
            _make_record(started_at=datetime(2026, 7, 28, 1, 0, tzinfo=UTC))
        )
        assert recorder.flush()

        assert len(storage.keys_for_day("2026-07-27")) == 1
        assert len(storage.keys_for_day("2026-07-28")) == 1

    def test_every_record_gets_a_distinct_id(self, recorder, storage) -> None:
        recorder.record(_make_record())
        recorder.record(_make_record())
        assert recorder.flush()

        first, second = storage.records()
        assert first["id"] != second["id"]

    def test_storage_failure_does_not_propagate(self, config) -> None:
        recorder = FileTraceRecorder(ExplodingStorage(), config)
        try:
            recorder.record(_make_record())  # must not raise
            # flush() must still return rather than hang on a dead backend.
            assert recorder.flush()
        finally:
            recorder.close()

    def test_an_unserializable_record_is_skipped_not_fatal(
        self, recorder, storage
    ) -> None:
        """One bad record must not cost the rest of its batch."""

        class Unserializable:
            def __str__(self) -> str:
                raise RuntimeError("cannot stringify")

        recorder.record(_make_record(context={"bad": Unserializable()}))
        recorder.record(_make_record())
        assert recorder.flush()

        written = storage.records()
        assert len(written) == 1
        assert written[0]["context"] == {
            "source": "ai.decompose_query",
            "interaction_id": "abc",
        }

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

    def test_records_land_in_a_readable_jsonl_object(self, tmp_path, config) -> None:
        storage = LocalStorageBackend(tmp_path)
        recorder = FileTraceRecorder(storage, config)
        try:
            recorder.record(_make_record())
            recorder.record(_make_record(model="zai-org/GLM-5.2"))
            assert recorder.flush()
        finally:
            recorder.close()

        day = tmp_path / "llm-traces" / "2026-07-27"
        (written_file,) = list(day.glob("*.jsonl"))

        records = [
            json.loads(line)
            for line in written_file.read_text(encoding="utf-8").splitlines()
        ]
        assert len(records) == 2
        assert records[0]["messages"][0]["content"] == "Vad gäller?"
        assert records[1]["model"] == "zai-org/GLM-5.2"

    def test_swedish_characters_survive_the_round_trip(self, tmp_path, config) -> None:
        storage = LocalStorageBackend(tmp_path)
        recorder = FileTraceRecorder(storage, config)
        try:
            recorder.record(
                _make_record(messages=(Message(role=Role.user, content="Växjö åäö"),))
            )
            assert recorder.flush()
        finally:
            recorder.close()

        (written_file,) = list((tmp_path / "llm-traces" / "2026-07-27").glob("*.jsonl"))
        raw = written_file.read_text(encoding="utf-8")

        assert "Växjö åäö" in raw  # not \uXXXX-escaped
        assert json.loads(raw)["messages"][0]["content"] == "Växjö åäö"


class TestInstallFileTracing:
    @pytest.fixture(autouse=True)
    def _close_whatever_got_installed(self):
        """Install leaves a writer thread and an `atexit` hook behind.

        Resetting the module global is not enough — an unclosed recorder outlives
        the test that made it, so the suite accumulates one thread per install.
        """
        set_trace_recorder(None)
        yield
        recorder = get_trace_recorder()
        # `get_trace_recorder` is typed to the protocol, which has no `close` —
        # only the file recorder owns a thread that needs shutting down.
        if isinstance(recorder, FileTraceRecorder):
            recorder.close()
        set_trace_recorder(None)

    def test_disabled_installs_nothing(self, storage) -> None:
        result = install_file_tracing(
            storage, LLMTraceConfig(enabled=False, key_prefix="llm-traces")
        )

        assert result is None
        assert get_trace_recorder() is None

    def test_enabled_installs_the_recorder(self, storage, config) -> None:
        recorder = install_file_tracing(storage, config)

        assert recorder is not None
        assert get_trace_recorder() is recorder

    def test_installing_twice_reuses_the_first_recorder(self, storage, config) -> None:
        """One process, one writer thread — however many main()s composed it."""
        first = install_file_tracing(storage, config)
        second = install_file_tracing(FakeStorage(), config)

        assert second is first
        assert get_trace_recorder() is first

    def test_unbuildable_backend_leaves_tracing_off_rather_than_failing(
        self, monkeypatch
    ) -> None:
        """Observability must never stop a process from starting."""
        monkeypatch.setattr(
            "ai._observability.create_storage_backend",
            lambda settings: (_ for _ in ()).throw(RuntimeError("no bucket")),
        )

        result = install_file_tracing(config=LLMTraceConfig(enabled=True))

        assert result is None
        assert get_trace_recorder() is None

    def test_a_backend_that_fails_at_write_time_still_installs(self, config) -> None:
        """Writes fail silently in the background; the process is unaffected."""
        recorder = install_file_tracing(ExplodingStorage(), config)

        assert recorder is not None
        recorder.record(_make_record())
        assert recorder.flush()
