"""The SQL endpoint's correlation contract.

The agent behind it is reached two ways — directly here, and as the
conversational agent's `query_corpus` tool. This route is the standalone case,
where there is no enclosing interaction to join and one has to be opened.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from agents import SqlAgentResult
from fastapi.testclient import TestClient
from llm_core._tracing import LLMCallRecord, set_trace_recorder
from sqlalchemy.ext.asyncio import AsyncSession

from api.correlation import INTERACTION_ID_HEADER
from api.dependencies import get_db
from api.main import create_app

SUPPLIED_ID = "11111111-1111-4111-8111-111111111111"


def _make_client():
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


class TestInteractionIdHeader:
    def setup_method(self):
        self.app, self.client = _make_client()
        self.seen: list[LLMCallRecord] = []

    def teardown_method(self):
        set_trace_recorder(None)
        self.app.dependency_overrides.clear()

    def _post(self, headers: dict[str, str] | None = None):
        result = SqlAgentResult(answered=False, sql=None, note="ingen fråga")
        with patch("api.routes.sql.run_sql_agent", new=AsyncMock(return_value=result)):
            return self.client.post(
                "/api/sql",
                json={"question": "Hur många avslogs 2026?"},
                headers=headers or {},
            )

    def test_a_supplied_uuid_is_honoured_and_echoed(self):
        response = self._post({INTERACTION_ID_HEADER: SUPPLIED_ID})

        assert response.status_code == 200
        assert response.headers[INTERACTION_ID_HEADER] == SUPPLIED_ID

    def test_an_absent_header_mints_one_and_returns_it(self):
        response = self._post()

        uuid.UUID(response.headers[INTERACTION_ID_HEADER])

    def test_a_non_uuid_is_ignored_and_the_replacement_is_returned(self):
        response = self._post({INTERACTION_ID_HEADER: "../../etc/passwd"})

        returned = response.headers[INTERACTION_ID_HEADER]
        assert returned != "../../etc/passwd"
        uuid.UUID(returned)

    def test_the_agent_runs_inside_the_returned_interaction(self):
        """The header is only useful if the traces carry the same id."""
        captured: list[str] = []

        async def _capture_context(*_args, **_kwargs):
            from llm_core import current_trace_context

            captured.append(current_trace_context()["interaction_id"])
            return SqlAgentResult(answered=False, sql=None, note="ingen fråga")

        with patch("api.routes.sql.run_sql_agent", new=_capture_context):
            response = self.client.post(
                "/api/sql",
                json={"question": "Hur många?"},
                headers={INTERACTION_ID_HEADER: SUPPLIED_ID},
            )

        assert response.headers[INTERACTION_ID_HEADER] == SUPPLIED_ID
        assert captured == [SUPPLIED_ID]
