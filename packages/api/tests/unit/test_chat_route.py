from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from agents.chat import (
    ChatTool,
    DoneEvent,
    ErrorEvent,
    ProgressLabel,
    SourceReference,
    SourcesEvent,
    SqlEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolStatus,
)
from ai import SynthesizeRequest, synthesize_answer, trace_context
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
from shared.dtos.session import SessionRead
from shared.enums import ChunkSection
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.main import create_app
from api.routes.chat import _format_sse

_DOCUMENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


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
    app.state.read_llm_provider = MagicMock()
    app.state.sql_llm_provider = MagicMock()
    app.state.storage = MagicMock()

    mock_db = AsyncMock(spec=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app)


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


def _agent_emitting(*events):
    async def _gen(*_args, **_kwargs):
        for event in events:
            yield event

    return _gen


def _source() -> SourceReference:
    return SourceReference(
        document_id=_DOCUMENT_ID,
        case_number="12/2024",
        excerpt="Nämnden avslår överklagandet.",
        section=ChunkSection.BODY,
    )


class TestFormatSse:
    def test_basic_format(self):
        result = _format_sse("token", {"text": "hello"})
        assert result == 'event: token\ndata: {"text": "hello"}\n\n'

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


class TestChatEndpointSseStream:
    def setup_method(self):
        self.chat_session = _make_session()
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def _post(self, agent, message="Vad gäller?"):
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch("api.routes.chat.append_turn", new=AsyncMock()),
            patch("api.routes.chat.run_chat_agent", agent),
        ):
            return self.client.post("/api/chat", json={"message": message})

    def test_progress_then_tokens_then_sources_then_done(self):
        response = self._post(
            _agent_emitting(
                ToolCallEvent(
                    id="tc-1",
                    tool=ChatTool.SEARCH_DECISIONS,
                    label=ProgressLabel.SEARCH_BROAD,
                    detail={"has_filter": False},
                ),
                ToolResultEvent(
                    id="tc-1",
                    tool=ChatTool.SEARCH_DECISIONS,
                    label=ProgressLabel.SEARCH_BROAD,
                    detail={"decision_count": 7},
                ),
                TokenEvent(text="Hej"),
                TokenEvent(text=" världen"),
                SourcesEvent(sources=[_source()]),
                DoneEvent(),
            )
        )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert [e["event"] for e in events] == [
            "tool_call",
            "tool_result",
            "token",
            "token",
            "sources",
            "done",
        ]

    def test_progress_events_carry_the_label_key_and_correlate_by_id(self):
        response = self._post(
            _agent_emitting(
                ToolCallEvent(
                    id="tc-1",
                    tool=ChatTool.QUERY_CORPUS,
                    label=ProgressLabel.SQL_QUERY,
                ),
                ToolResultEvent(
                    id="tc-1",
                    tool=ChatTool.QUERY_CORPUS,
                    label=ProgressLabel.SQL_QUERY,
                    status=ToolStatus.OK,
                    detail={"row_count": 12},
                ),
                DoneEvent(),
            )
        )

        events = _parse_sse(response.text)
        call, result = events[0]["data"], events[1]["data"]
        assert call["label"] == "sql.query"
        assert call["tool"] == "query_corpus"
        assert call["id"] == result["id"]
        assert result["status"] == "ok"

    def test_no_progress_event_carries_user_facing_prose(self):
        """The API emits keys; the client owns the words."""
        response = self._post(
            _agent_emitting(
                ToolCallEvent(
                    id="tc-1",
                    tool=ChatTool.SEARCH_DECISIONS,
                    label=ProgressLabel.SEARCH_FILTERED,
                    detail={"has_filter": True, "filter_fields": ["category"]},
                ),
                DoneEvent(),
            )
        )

        payload = _parse_sse(response.text)[0]["data"]
        assert set(payload) == {"type", "id", "tool", "label", "detail"}
        # Nothing in the frame is a sentence: every string is a key or an
        # identifier, so a client cannot accidentally render one.
        for value in payload["detail"].values():
            assert not isinstance(value, str)

    def test_sql_event_precedes_the_answer(self):
        response = self._post(
            _agent_emitting(
                SqlEvent(
                    answered=True,
                    sql="SELECT count(*) FROM documents",
                    columns=["antal"],
                    rows=[[12]],
                    row_count=1,
                ),
                TokenEvent(text="Tolv."),
                DoneEvent(),
            )
        )

        events = _parse_sse(response.text)
        names = [e["event"] for e in events]
        assert names.index("sql") < names.index("token")
        assert events[0]["data"]["sql"] == "SELECT count(*) FROM documents"

    def test_sources_carry_a_pdf_url_and_the_appendix_label(self):
        response = self._post(
            _agent_emitting(
                SourcesEvent(
                    sources=[
                        SourceReference(
                            document_id=_DOCUMENT_ID,
                            case_number="12/2024",
                            excerpt="Stiftet beslutade...",
                            section=ChunkSection.APPENDIX,
                            appendix_label="Bilaga A",
                        )
                    ]
                ),
                DoneEvent(),
            )
        )

        source = _parse_sse(response.text)[0]["data"]["sources"][0]
        assert source["pdf_url"] == f"/api/documents/{_DOCUMENT_ID}/pdf"
        assert source["section"] == "appendix"
        assert source["appendix_label"] == "Bilaga A"

    def test_done_carries_the_session_id(self):
        response = self._post(_agent_emitting(DoneEvent()))

        done = _parse_sse(response.text)[-1]
        assert done["event"] == "done"
        assert done["data"]["session_id"] == str(self.chat_session.id)

    def test_error_event_is_terminal_and_no_done_follows(self):
        response = self._post(
            _agent_emitting(
                TokenEvent(text="Hej"),
                ErrorEvent(message="Ett fel uppstod när frågan besvarades."),
            )
        )

        events = _parse_sse(response.text)
        assert [e["event"] for e in events] == ["token", "error"]
        assert not any(e["event"] == "done" for e in events)

    def test_mid_stream_failure_emits_a_safe_error_event(self):
        async def _failing(*_args, **_kwargs):
            yield TokenEvent(text="Hej")
            raise RuntimeError("provider exploded with secrets in the message")

        response = self._post(_failing)

        events = _parse_sse(response.text)
        assert events[-1]["event"] == "error"
        assert "secrets" not in events[-1]["data"]["message"]

    def test_sse_headers(self):
        response = self._post(_agent_emitting(DoneEvent()))

        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"

    def test_completed_turn_is_persisted(self):
        append = AsyncMock()
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch("api.routes.chat.append_turn", append),
            patch(
                "api.routes.chat.run_chat_agent",
                _agent_emitting(
                    TokenEvent(text="Hej"), TokenEvent(text="!"), DoneEvent()
                ),
            ),
        ):
            self.client.post("/api/chat", json={"message": "Vad gäller?"})

        append.assert_awaited_once()
        call = append.await_args
        assert call is not None
        assert call.args[1] == "Vad gäller?"
        assert call.args[2] == "Hej!"

    def test_failed_turn_is_not_persisted(self):
        append = AsyncMock()
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch("api.routes.chat.append_turn", append),
            patch(
                "api.routes.chat.run_chat_agent",
                _agent_emitting(ErrorEvent(message="fel")),
            ),
        ):
            self.client.post("/api/chat", json={"message": "Vad gäller?"})

        append.assert_not_awaited()


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

    def _agent_making_real_calls(self):
        """Stands in for the agent, making the calls it would make."""

        async def _gen(*_args, **_kwargs):
            structured = AsyncMock()
            structured.generate = AsyncMock(
                return_value=LLMResponse(
                    message=Message(
                        role=Role.assistant, content='{"ranked_indices": []}'
                    )
                )
            )

            with trace_context(source="agents.chat"):
                await generate_structured(
                    [Message(role=Role.user, content="plan")],
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

    def _post(self):
        with (
            patch(
                "api.routes.chat.get_or_create_session", return_value=self.chat_session
            ),
            patch("api.routes.chat.append_turn", new=AsyncMock()),
            patch("api.routes.chat.run_chat_agent", self._agent_making_real_calls()),
        ):
            return self.client.post("/api/chat", json={"message": "Vad gäller?"})

    def test_every_call_shares_one_interaction_id(self):
        response = self._post()

        assert response.status_code == 200
        assert len(self.records) == 2
        assert len({r.context["interaction_id"] for r in self.records}) == 1
        assert {r.context["source"] for r in self.records} == {
            "agents.chat",
            "ai.synthesize_answer",
        }

    def test_records_carry_the_session_id(self):
        self._post()

        assert {r.context["session_id"] for r in self.records} == {
            str(self.chat_session.id)
        }
