"""The conversation-list routes, against a mocked service layer.

What is worth testing here is the wire contract rather than the folding, which
`test_session_service.py` covers: an unknown id is a 404 and not an empty
transcript, a delete that removed nothing is a 404 and not a cheerful 204, and
the list is the same `Page` shape every other list endpoint returns.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from shared.dtos.session import SessionSummary, SessionTranscript, SessionTurn
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.main import create_app
from api.pagination import Page

_SESSION_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _make_client() -> TestClient:
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
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return _make_client()


def _summary(title: str = "Vad gäller vid jäv?") -> SessionSummary:
    return SessionSummary(
        id=_SESSION_ID,
        created_at=_NOW,
        last_active_at=_NOW,
        title=title,
        turn_count=3,
    )


class TestListSessions:
    def test_returns_a_page_of_summaries(self, client: TestClient):
        page = Page[SessionSummary](items=[_summary()], total=1, limit=20, offset=0)
        with patch(
            "api.routes.sessions.list_sessions", AsyncMock(return_value=page)
        ) as service:
            response = client.get("/api/sessions")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Vad gäller vid jäv?"
        assert body["items"][0]["turn_count"] == 3
        assert service.await_count == 1

    def test_no_history_field_is_exposed(self, client: TestClient):
        """The list is a list. Pulling transcripts to draw one is the mistake
        `SessionSummary` exists to prevent, and the wire shape should show it."""
        page = Page[SessionSummary](items=[_summary()], total=1, limit=20, offset=0)
        with patch("api.routes.sessions.list_sessions", AsyncMock(return_value=page)):
            body = client.get("/api/sessions").json()

        assert "history" not in body["items"][0]
        assert "turns" not in body["items"][0]

    def test_paging_reaches_the_service(self, client: TestClient):
        page = Page[SessionSummary](items=[], total=0, limit=5, offset=10)
        with patch(
            "api.routes.sessions.list_sessions", AsyncMock(return_value=page)
        ) as service:
            client.get("/api/sessions?limit=5&offset=10")

        service.assert_awaited_once_with(ANY, limit=5, offset=10)

    def test_rejects_a_negative_offset(self, client: TestClient):
        assert client.get("/api/sessions?offset=-1").status_code == 422


class TestSessionTranscript:
    def test_returns_the_turns(self, client: TestClient):
        transcript = SessionTranscript(
            id=_SESSION_ID,
            created_at=_NOW,
            last_active_at=_NOW,
            turns=[SessionTurn(question="q", answer="a", interaction_id="i1")],
        )
        with patch(
            "api.routes.sessions.get_transcript", AsyncMock(return_value=transcript)
        ):
            response = client.get(f"/api/sessions/{_SESSION_ID}")

        assert response.status_code == 200
        assert response.json()["turns"] == [
            {"question": "q", "answer": "a", "interaction_id": "i1"}
        ]

    def test_carries_no_evidence(self, client: TestClient):
        """A turn is a question and an answer. The passages it rested on are not
        stored, so there is no field here that could imply otherwise."""
        transcript = SessionTranscript(
            id=_SESSION_ID,
            created_at=_NOW,
            last_active_at=_NOW,
            turns=[SessionTurn(question="q", answer="a", interaction_id=None)],
        )
        with patch(
            "api.routes.sessions.get_transcript", AsyncMock(return_value=transcript)
        ):
            turn = client.get(f"/api/sessions/{_SESSION_ID}").json()["turns"][0]

        assert set(turn) == {"question", "answer", "interaction_id"}

    def test_unknown_session_is_404(self, client: TestClient):
        with patch("api.routes.sessions.get_transcript", AsyncMock(return_value=None)):
            response = client.get(f"/api/sessions/{uuid.uuid4()}")

        assert response.status_code == 404

    def test_unparseable_id_is_422(self, client: TestClient):
        assert client.get("/api/sessions/not-a-uuid").status_code == 422


class TestDeleteSession:
    def test_removed_session_is_204(self, client: TestClient):
        with patch(
            "api.routes.sessions.delete_session", AsyncMock(return_value=True)
        ) as service:
            response = client.delete(f"/api/sessions/{_SESSION_ID}")

        assert response.status_code == 204
        assert response.content == b""
        service.assert_awaited_once_with(_SESSION_ID, ANY)

    def test_unknown_session_is_404(self, client: TestClient):
        """Reporting success for a delete that removed nothing would let a stale
        rail believe it had pruned something it had not."""
        with patch("api.routes.sessions.delete_session", AsyncMock(return_value=False)):
            response = client.delete(f"/api/sessions/{uuid.uuid4()}")

        assert response.status_code == 404
