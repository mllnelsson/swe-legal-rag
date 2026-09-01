from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from agent_kit.llm import (
    LLMCallRecord,
    LLMOperation,
    Message,
    Role,
    ToolCall,
    Usage,
    get_trace_recorder,
    set_trace_recorder,
)

from ai._observability import (
    TRACE_SCHEMA_VERSION,
    FileTraceRecorder,
    LLMTraceConfig,
    install_file_tracing,
    serialize_record,
)

RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

# {date}/{interaction_id}/{time}-{source}-{id8}.json
TRACE_PATH = re.compile(
    r"^\d{4}-\d{2}-\d{2}/[A-Za-z0-9._-]+/\d{6}\.\d{6}-[A-Za-z0-9._-]+-[0-9a-f]{8}\.json$"
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


def _written(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def _payloads(root: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in _written(root)]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "llm-traces"


@pytest.fixture
def recorder(root: Path) -> FileTraceRecorder:
    return FileTraceRecorder(root)


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


class TestLayout:
    """The directory carries the correlation, so nothing has to index it."""

    def test_one_file_per_call(self, recorder, root) -> None:
        recorder.record(_make_record())
        recorder.record(_make_record())

        assert len(_written(root)) == 2

    def test_path_is_date_then_interaction_then_call(self, recorder, root) -> None:
        recorder.record(_make_record())

        (written,) = _written(root)
        assert TRACE_PATH.match(str(written.relative_to(root)))

    def test_one_request_is_one_directory(self, recorder, root) -> None:
        """The whole point: what a request cost is a sum over one folder."""
        for source in ("agents.chat", "agents.sql", "ai.synthesize_answer"):
            recorder.record(
                _make_record(context={"source": source, "interaction_id": "turn-1"})
            )
        recorder.record(
            _make_record(context={"source": "agents.chat", "interaction_id": "turn-2"})
        )

        turn = root / "2026-07-27" / "turn-1"
        assert len(list(turn.glob("*.json"))) == 3
        assert len(list((root / "2026-07-27" / "turn-2").glob("*.json"))) == 1

    def test_filenames_sort_into_call_order(self, recorder, root) -> None:
        for minute, source in enumerate(["agents.chat", "agents.sql", "agents.chat"]):
            recorder.record(
                _make_record(
                    started_at=datetime(2026, 7, 27, 10, minute, 0, tzinfo=UTC),
                    context={"source": source, "interaction_id": "turn-1"},
                )
            )

        names = [p.name for p in _written(root)]
        assert [n.split("-")[1] for n in names] == [
            "agents.chat",
            "agents.sql",
            "agents.chat",
        ]

    def test_records_in_the_same_microsecond_do_not_collide(
        self, recorder, root
    ) -> None:
        """Timestamps are unique only while calls are sequential."""
        moment = datetime(2026, 7, 27, 10, 15, 33, 123456, tzinfo=UTC)
        recorder.record(_make_record(started_at=moment))
        recorder.record(_make_record(started_at=moment))

        assert len(_written(root)) == 2

    def test_a_record_with_no_interaction_is_still_written(
        self, recorder, root
    ) -> None:
        """A gap in the wiring should be visible on disk, not silently dropped."""
        recorder.record(_make_record(context={"source": "ai.embed"}))

        (written,) = _written(root)
        assert written.parent.name == "_unscoped"

    def test_records_land_in_their_own_day(self, recorder, root) -> None:
        recorder.record(
            _make_record(started_at=datetime(2026, 7, 27, 23, 59, 59, tzinfo=UTC))
        )
        recorder.record(
            _make_record(started_at=datetime(2026, 7, 28, 0, 0, 1, tzinfo=UTC))
        )

        assert {p.parent.parent.name for p in _written(root)} == {
            "2026-07-27",
            "2026-07-28",
        }

    def test_a_hostile_interaction_id_cannot_escape_the_root(
        self, recorder, root
    ) -> None:
        """The id can reach here from a request header."""
        recorder.record(
            _make_record(context={"source": "ai.embed", "interaction_id": "../../etc"})
        )

        (written,) = _written(root)
        assert root in written.parents


class TestWriting:
    def test_the_record_round_trips(self, recorder, root) -> None:
        recorder.record(_make_record())

        (payload,) = _payloads(root)
        assert payload["model"] == "gemini-2.5-flash-lite"
        assert payload["usage"]["input_tokens"] == 1200
        assert payload["context"]["interaction_id"] == "abc"

    def test_swedish_characters_survive_the_round_trip(self, recorder, root) -> None:
        recorder.record(
            _make_record(
                messages=(Message(role=Role.user, content="Vad gäller om jäv?"),)
            )
        )

        (written,) = _written(root)
        raw = written.read_text(encoding="utf-8")
        assert "Vad gäller om jäv?" in raw
        assert "\\u00e4" not in raw

    def test_every_record_gets_a_distinct_id(self, recorder, root) -> None:
        recorder.record(_make_record())
        recorder.record(_make_record())

        ids = {payload["id"] for payload in _payloads(root)}
        assert len(ids) == 2

    def test_no_partial_file_is_left_behind(self, recorder, root) -> None:
        """Written under a temporary name, then moved into place."""
        recorder.record(_make_record())

        assert not list(root.rglob("*.tmp"))

    def test_a_write_failure_does_not_propagate(self, root) -> None:
        """Observability failing must never fail the call it describes."""
        root.parent.mkdir(parents=True, exist_ok=True)
        root.write_text("not a directory")

        FileTraceRecorder(root).record(_make_record())

    def test_an_unserializable_record_is_not_fatal(self, recorder, root) -> None:
        class Exploding:
            def __repr__(self) -> str:
                raise RuntimeError("nope")

        recorder.record(_make_record(context={"weird": Exploding()}))

        assert _written(root) == []


class TestInstallFileTracing:
    @pytest.fixture(autouse=True)
    def _reset(self):
        yield
        set_trace_recorder(None)

    def test_disabled_installs_nothing(self, root) -> None:
        assert install_file_tracing(root, LLMTraceConfig(enabled=False)) is None
        assert get_trace_recorder() is None

    def test_enabled_installs_the_recorder(self, root) -> None:
        recorder = install_file_tracing(root, LLMTraceConfig(enabled=True))

        assert isinstance(recorder, FileTraceRecorder)
        assert get_trace_recorder() is recorder

    def test_installing_twice_reuses_the_first_recorder(self, root) -> None:
        """`run_pipeline.py` composes several worker `main()`s in one process."""
        first = install_file_tracing(root, LLMTraceConfig(enabled=True))
        second = install_file_tracing(root, LLMTraceConfig(enabled=True))

        assert first is second

    def test_an_unusable_root_leaves_tracing_off_rather_than_failing(
        self, tmp_path
    ) -> None:
        blocked = tmp_path / "file"
        blocked.write_text("not a directory")

        assert install_file_tracing(blocked / "traces", LLMTraceConfig()) is None
        assert get_trace_recorder() is None
