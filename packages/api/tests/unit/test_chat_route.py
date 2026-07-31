from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from ai import SynthesizeRequest, decompose_query, synthesize_answer, trace_context
from fastapi.testclient import TestClient
from llm_core import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    generate_structured,
    set_trace_recorder,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.main import create_app
from api.routes.chat import _format_sse, _get_db
from api.services.answerer import DoneEvent, SourcesEvent, TokenEvent
from shared.dtos.session import SessionRead


class _RankStub(BaseModel):
    ranked_indices: list[int] = []


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
    app.state.structured_llm_provider = MagicMock()
    app.state.chat_llm_provider = MagicMock()
    app.state.storage = MagicMock()

    mock_db = AsyncMock(spec=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[_get_db] = override_get_db
    return app, TestClient(app)


class TestFormatSse:
    def test_basic_format(self):
        result = _format_sse("token", {"text": "hello"})
        assert result == 'event: token\ndata: {"text": "hello"}\n\n'

    def test_data_is_json_encoded(self):
        result = _format_sse("sources", {"sources": []})
        assert "data: " in result
        data_line = [ln for ln in result.split("\n") if ln.startswith("data:")][0]
        parsed = json.loads(data_line[len("data: ") :])
        assert parsed == {"sources": []}

    def test_event_name_in_output(self):
        result = _format_sse("done", {"session_id": "abc"})
        assert result.startswith("event: done\n")

    def test_ends_with_double_newline(self):
        result = _format_sse("token", {"text": "x"})
        assert result.endswith("\n\n")

    def test_unicode_content_round_trips(self):
        swedish = "kyrkorätten säger: åäö"
        result = _format_sse("token", {"text": swedish})
        data_line = [ln for ln in result.split("\n") if ln.startswith("data:")][0]
        parsed = json.loads(data_line[len("data: ") :])
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
        response = self.client.post(
            "/api/chat", json={"message": "hi", "session_id": "not-a-uuid"}
        )
        assert response.status_code == 422


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE stream text into list of {event, data} dicts."""
    events = []
    current: dict = {}
    for line in text.split("\n"):
        if line.startswith("event: "):
            current["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current["data"] = json.loads(line[len("data: ") :])
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
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch(
                "api.routes.chat.answer_query",
                self._fake_answer_query(tokens=["Hej", " världen"]),
            ),
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
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        events = _parse_sse(response.text)
        token_idxs = [i for i, e in enumerate(events) if e["event"] == "token"]
        source_idxs = [i for i, e in enumerate(events) if e["event"] == "sources"]
        assert source_idxs[0] > token_idxs[-1]

    def test_done_event_last_with_session_id(self):
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
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
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ) as mock_create,
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            self.client.post("/api/chat", json={"message": "test", "session_id": None})

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args.args[0] is None

    def test_existing_session_id_passed_to_get_or_create(self):
        existing_id = uuid.uuid4()
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ) as mock_create,
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            self.client.post(
                "/api/chat", json={"message": "test", "session_id": str(existing_id)}
            )

        mock_create.assert_called_once()
        assert mock_create.call_args.args[0] == existing_id

    def test_response_content_type_is_event_stream(self):
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch("api.routes.chat.answer_query", self._fake_answer_query()),
        ):
            response = self.client.post("/api/chat", json={"message": "test"})

        assert "text/event-stream" in response.headers["content-type"]

    def test_no_cache_headers_set(self):
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
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
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
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
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
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
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
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
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
        ):
            response = self.client.post("/api/chat", json={"message": ""})

        assert response.status_code == 422


class TestHealthz:
    def test_healthz_returns_200(self):
        app = create_app()
        # Entering TestClient runs lifespan, which verifies the embedding dimension.
        # Stubbed out here: the real check loads the ~2.2 GB model, which this test
        # has no use for. Coverage for the check itself lives in the ai package.
        with (
            patch("ai.create_embedding_provider", return_value=MagicMock()),
            patch("ai.verify_embedding_dimension", new=AsyncMock(return_value=1024)),
            TestClient(app) as client,
        ):
            response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestChatTracing:
    """One question, one interaction id — the basis for costing a question.

    The trace context is entered inside the SSE generator, which Starlette
    drives after the route handler has already returned. These tests exist to
    prove that context still reaches every nested call, including the streaming
    synthesis that outlives the handler body.
    """

    def setup_method(self):
        self.chat_session = _make_session()
        self.app, self.client = _make_client()
        self.records = []

        class Recording:
            def record(inner, record):
                self.records.append(record)

        set_trace_recorder(Recording())

    def teardown_method(self):
        set_trace_recorder(None)
        self.app.dependency_overrides.clear()

    def _answer_query_making_real_calls(self):
        """Stands in for the retrieval pipeline, making the calls it would make."""

        async def _gen(*args, **kwargs):
            structured = AsyncMock()
            structured.generate = AsyncMock(
                return_value=LLMResponse(
                    message=Message(
                        role=Role.assistant,
                        content=(
                            '{"categories": [], "entity_refs": [],'
                            ' "semantic_query": "kyrka"}'
                        ),
                    )
                )
            )
            await decompose_query("Vad gäller?", provider=structured)

            with trace_context(source="api.retriever.rerank"):
                await generate_structured(
                    [Message(role=Role.user, content="rank")],
                    _RankStub,
                    provider=structured,
                )

            async def _stream(*_args, **_kwargs):
                for text in ["Sva", "r"]:
                    yield StreamChunk(text=text)

            chat = AsyncMock()
            chat.generate_stream = AsyncMock(side_effect=_stream)
            request = SynthesizeRequest(question="Vad gäller?", chunks=[])
            async for token in synthesize_answer(request, provider=chat):
                yield TokenEvent(text=token)

            yield SourcesEvent(sources=[])
            yield DoneEvent()

        return _gen

    def test_every_call_shares_one_interaction_id(self):
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch(
                "api.routes.chat.answer_query",
                self._answer_query_making_real_calls(),
            ),
        ):
            response = self.client.post("/api/chat", json={"message": "Vad gäller?"})

        assert response.status_code == 200
        assert len(self.records) == 3
        assert len({r.context["interaction_id"] for r in self.records}) == 1
        assert {r.context["source"] for r in self.records} == {
            "ai.decompose_query",
            "api.retriever.rerank",
            "ai.synthesize_answer",
        }

    def test_records_carry_the_session_id(self):
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch(
                "api.routes.chat.answer_query",
                self._answer_query_making_real_calls(),
            ),
        ):
            self.client.post("/api/chat", json={"message": "Vad gäller?"})

        assert {r.context["session_id"] for r in self.records} == {
            str(self.chat_session.id)
        }

    def test_streamed_answer_is_captured_whole(self):
        """The streaming call outlives the handler; its record must still land."""
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch(
                "api.routes.chat.answer_query",
                self._answer_query_making_real_calls(),
            ),
        ):
            self.client.post("/api/chat", json={"message": "Vad gäller?"})

        synthesis = [
            r for r in self.records if r.context["source"] == "ai.synthesize_answer"
        ]
        assert len(synthesis) == 1
        assert synthesis[0].response_text == "Svar"
        assert synthesis[0].success is True

    def test_two_questions_get_two_interaction_ids(self):
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch(
                "api.routes.chat.answer_query",
                self._answer_query_making_real_calls(),
            ),
        ):
            self.client.post("/api/chat", json={"message": "Första frågan"})
            self.client.post("/api/chat", json={"message": "Andra frågan"})

        assert len({r.context["interaction_id"] for r in self.records}) == 2
