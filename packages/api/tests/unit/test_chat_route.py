from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.main import create_app
from api.routes.chat import format_sse, get_db
from api.services.answerer import DoneEvent, SourcesEvent, TokenEvent
from shared.dtos.session import SessionRead


def _make_session(session_id: uuid.UUID | None = None) -> SessionRead:
    now = datetime.now(timezone.utc)
    return SessionRead(
        id=session_id or uuid.uuid4(),
        created_at=now,
        last_active_at=now,
        history=[],
    )


def _make_client():
    """Return a TestClient with all IO dependencies mocked."""
    app = create_app()

    app.state.embedding_provider = MagicMock()
    app.state.storage = MagicMock()

    mock_db = AsyncMock(spec=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app)


class TestFormatSse:
    def test_basic_format(self):
        result = format_sse("token", {"text": "hello"})
        assert result == 'event: token\ndata: {"text": "hello"}\n\n'

    def test_data_is_json_encoded(self):
        result = format_sse("sources", {"sources": []})
        assert "data: " in result
        data_line = [ln for ln in result.split("\n") if ln.startswith("data:")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed == {"sources": []}

    def test_event_name_in_output(self):
        result = format_sse("done", {"session_id": "abc"})
        assert result.startswith("event: done\n")

    def test_ends_with_double_newline(self):
        result = format_sse("token", {"text": "x"})
        assert result.endswith("\n\n")

    def test_unicode_content_round_trips(self):
        swedish = "kyrkorätten säger: åäö"
        result = format_sse("token", {"text": swedish})
        data_line = [ln for ln in result.split("\n") if ln.startswith("data:")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed["text"] == swedish


class TestChatEndpointValidation:
    def setup_method(self):
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def test_empty_message_returns_422(self):
        response = self.client.post("/api/chat", json={"message": ""})
        assert response.status_code == 422

    def test_message_too_long_returns_422(self):
        response = self.client.post("/api/chat", json={"message": "x" * 4001})
        assert response.status_code == 422

    def test_missing_message_returns_422(self):
        response = self.client.post("/api/chat", json={})
        assert response.status_code == 422

    def test_invalid_session_id_returns_422(self):
        response = self.client.post("/api/chat", json={"message": "hi", "session_id": "not-a-uuid"})
        assert response.status_code == 422


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE stream text into list of {event, data} dicts."""
    events = []
    current: dict = {}
    for line in text.split("\n"):
        if line.startswith("event: "):
            current["event"] = line[len("event: "):]
        elif line.startswith("data: "):
            current["data"] = json.loads(line[len("data: "):])
        elif line == "" and current:
            events.append(current)
            current = {}
    return events


class TestChatEndpointSseStream:
    def setup_method(self):
        self.chat_session = _make_session()
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def _fake_answer_query(self, tokens=("hello", " world"), sources=None):
        sources = sources or []

        async def _gen(*args, **kwargs):
            for t in tokens:
                yield TokenEvent(text=t)
            yield SourcesEvent(sources=sources)
            yield DoneEvent()

        return _gen

    def test_token_events_streamed(self):
        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
            patch("api.routes.chat.answer_query", self._fake_answer_query(tokens=["Hej", " världen"])),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        assert response.status_code == 200
        events = _parse_sse(response.text)
        token_events = [e for e in events if e["event"] == "token"]
        assert len(token_events) == 2
        assert token_events[0]["data"]["text"] == "Hej"
        assert token_events[1]["data"]["text"] == " världen"

    def test_sources_event_after_tokens(self):
        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        events = _parse_sse(response.text)
        token_idxs = [i for i, e in enumerate(events) if e["event"] == "token"]
        source_idxs = [i for i, e in enumerate(events) if e["event"] == "sources"]
        assert source_idxs[0] > token_idxs[-1]

    def test_done_event_last_with_session_id(self):
        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        events = _parse_sse(response.text)
        done_events = [e for e in events if e["event"] == "done"]
        assert len(done_events) == 1
        assert done_events[0]["data"]["session_id"] == str(self.chat_session.id)
        assert events[-1]["event"] == "done"

    def test_null_session_id_creates_new_session(self):
        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session) as mock_create,
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            self.client.post("/api/chat", json={"message": "test", "session_id": None})

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args.args[0] is None

    def test_existing_session_id_passed_to_get_or_create(self):
        existing_id = uuid.uuid4()
        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session) as mock_create,
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            self.client.post("/api/chat", json={"message": "test", "session_id": str(existing_id)})

        mock_create.assert_called_once()
        assert mock_create.call_args.args[0] == existing_id

    def test_response_content_type_is_event_stream(self):
        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        assert "text/event-stream" in response.headers["content-type"]

    def test_no_cache_headers_set(self):
        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"


class TestChatEndpointErrorHandling:
    def setup_method(self):
        self.chat_session = _make_session()
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def test_mid_stream_error_emits_error_event(self):
        async def _failing_answer_query(*args, **kwargs):
            yield TokenEvent(text="partial")
            raise RuntimeError("LLM provider failed")

        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
            patch("api.routes.chat.answer_query", _failing_answer_query),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        events = _parse_sse(response.text)
        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) == 1
        assert "message" in error_events[0]["data"]

    def test_no_done_after_mid_stream_error(self):
        async def _failing_answer_query(*args, **kwargs):
            yield TokenEvent(text="partial")
            raise RuntimeError("failure")

        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
            patch("api.routes.chat.answer_query", _failing_answer_query),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        events = _parse_sse(response.text)
        done_events = [e for e in events if e["event"] == "done"]
        assert len(done_events) == 0

    def test_error_message_is_safe_string(self):
        async def _failing_answer_query(*args, **kwargs):
            raise RuntimeError("Internal secret: password=1234")
            yield  # make it an async generator

        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
            patch("api.routes.chat.answer_query", _failing_answer_query),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        events = _parse_sse(response.text)
        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) == 1
        assert "password" not in error_events[0]["data"]["message"]
        assert "1234" not in error_events[0]["data"]["message"]

    def test_pre_stream_error_does_not_emit_error_event(self):
        """Validation errors before streaming → 422, not SSE error."""
        with (
            patch("api.routes.chat.get_or_create_session", return_value=self.chat_session),
        ):
            response = self.client.post("/api/chat", json={"message": ""})

        assert response.status_code == 422


class TestHealthz:
    def test_healthz_returns_200(self):
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
