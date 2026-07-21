from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai.dtos import DecomposeResult
from api.main import create_app
from api.routes.chat import _get_db
from shared.repositories import session as session_repo

pytestmark = pytest.mark.integration

_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/overklagan"
)


def _async_url(url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", url)


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in text.split("\n"):
        if line.startswith("event: "):
            current["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current["data"] = json.loads(line[len("data: ") :])
        elif line == "" and current:
            events.append(current)
            current = {}
    return events


async def _stream_chat(client: httpx.AsyncClient, body: dict) -> list[dict[str, Any]]:
    collected = ""
    async with client.stream("POST", "/api/chat", json=body) as response:
        assert response.status_code == 200
        async for chunk in response.aiter_text():
            collected += chunk
    return _parse_sse(collected)


@pytest.fixture
async def api_app(truncate_sessions) -> AsyncGenerator[Any, None]:
    engine = create_async_engine(_async_url(_DATABASE_URL))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app()
    app.state.embedding_provider = MagicMock()
    app.state.storage = MagicMock()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[_get_db] = _override_db
    yield app
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def http_client(api_app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="http://test",
    )


async def _load_session_from_db(session_id: uuid.UUID) -> Any:
    engine = create_async_engine(_async_url(_DATABASE_URL))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        result = await session_repo.get_by_id(s, session_id)
    await engine.dispose()
    return result


def _fake_decompose(semantic_query: str = "") -> Any:
    async def _inner(question: str, history=None, *, provider=None) -> DecomposeResult:
        return DecomposeResult(
            semantic_query=semantic_query or question,
            categories=[],
            entity_refs=[],
            filters=None,
        )

    return _inner


def _fake_synthesize(tokens: list[str]) -> Any:
    async def _inner(request, *, provider=None) -> AsyncIterator[str]:
        for t in tokens:
            yield t

    return _inner


_FAKE_RETRIEVE = "api.services.answerer.retrieve"
_FAKE_DECOMPOSE = "api.services.query_planner.ai.decompose_query"
_FAKE_SYNTHESIZE = "api.services.answerer.ai.synthesize_answer"

_SWEDISH_TOKENS = ["Kyrkan ", "regleras ", "av kyrkoordningen."]


class TestNewSessionRoundTrip:
    async def test_events_in_order(self, http_client: httpx.AsyncClient):
        with (
            patch(_FAKE_DECOMPOSE, side_effect=_fake_decompose()),
            patch(_FAKE_SYNTHESIZE, _fake_synthesize(_SWEDISH_TOKENS)),
            patch(_FAKE_RETRIEVE, return_value=[]),
        ):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        token_events = [e for e in events if e["event"] == "token"]
        sources_events = [e for e in events if e["event"] == "sources"]
        done_events = [e for e in events if e["event"] == "done"]

        assert len(token_events) == len(_SWEDISH_TOKENS)
        assert len(sources_events) == 1
        assert len(done_events) == 1

        token_idxs = [i for i, e in enumerate(events) if e["event"] == "token"]
        sources_idx = next(i for i, e in enumerate(events) if e["event"] == "sources")
        done_idx = next(i for i, e in enumerate(events) if e["event"] == "done")

        assert max(token_idxs) < sources_idx < done_idx

    async def test_done_carries_session_id(self, http_client: httpx.AsyncClient):
        with (
            patch(_FAKE_DECOMPOSE, side_effect=_fake_decompose()),
            patch(_FAKE_SYNTHESIZE, _fake_synthesize(_SWEDISH_TOKENS)),
            patch(_FAKE_RETRIEVE, return_value=[]),
        ):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        done = next(e for e in events if e["event"] == "done")
        assert "session_id" in done["data"]
        assert uuid.UUID(done["data"]["session_id"])

    async def test_history_persisted_to_db(self, http_client: httpx.AsyncClient):
        with (
            patch(_FAKE_DECOMPOSE, side_effect=_fake_decompose()),
            patch(_FAKE_SYNTHESIZE, _fake_synthesize(_SWEDISH_TOKENS)),
            patch(_FAKE_RETRIEVE, return_value=[]),
        ):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        session_id = uuid.UUID(
            next(e for e in events if e["event"] == "done")["data"]["session_id"]
        )
        db_session = await _load_session_from_db(session_id)

        assert db_session is not None
        assert len(db_session.history) == 2
        assert db_session.history[0] == {"role": "user", "content": "Vad gäller?"}
        assert db_session.history[1]["role"] == "assistant"
        assert "kyrkoordningen" in db_session.history[1]["content"]


class TestFollowUpConversation:
    async def test_prior_history_passed_to_decompose(
        self, http_client: httpx.AsyncClient
    ):
        captured_histories: list[list] = []

        async def _capturing_decompose(
            question, history=None, *, provider=None
        ) -> DecomposeResult:
            captured_histories.append(list(history or []))
            return DecomposeResult(
                semantic_query=question,
                categories=[],
                entity_refs=[],
                filters=None,
            )

        with (
            patch(_FAKE_DECOMPOSE, side_effect=_capturing_decompose),
            patch(_FAKE_SYNTHESIZE, _fake_synthesize(_SWEDISH_TOKENS)),
            patch(_FAKE_RETRIEVE, return_value=[]),
        ):
            first = await _stream_chat(http_client, {"message": "Vad gäller?"})
            session_id = next(e for e in first if e["event"] == "done")["data"][
                "session_id"
            ]

            await _stream_chat(
                http_client, {"message": "Berätta mer", "session_id": session_id}
            )

        assert len(captured_histories) == 2
        first_call_history = captured_histories[0]
        second_call_history = captured_histories[1]

        assert first_call_history == []
        assert len(second_call_history) == 2
        assert second_call_history[0]["role"] == "user"
        assert second_call_history[0]["content"] == "Vad gäller?"
        assert second_call_history[1]["role"] == "assistant"


class TestMidStreamFailure:
    async def _failing_synthesize(
        self, request, *, provider=None
    ) -> AsyncIterator[str]:
        yield "Partial "
        raise RuntimeError("LLM provider failed")

    async def test_error_event_emitted(self, http_client: httpx.AsyncClient):
        with (
            patch(_FAKE_DECOMPOSE, side_effect=_fake_decompose()),
            patch(_FAKE_SYNTHESIZE, self._failing_synthesize),
            patch(_FAKE_RETRIEVE, return_value=[]),
        ):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) == 1
        assert "message" in error_events[0]["data"]

    async def test_no_done_after_error(self, http_client: httpx.AsyncClient):
        with (
            patch(_FAKE_DECOMPOSE, side_effect=_fake_decompose()),
            patch(_FAKE_SYNTHESIZE, self._failing_synthesize),
            patch(_FAKE_RETRIEVE, return_value=[]),
        ):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        assert not any(e["event"] == "done" for e in events)

    async def test_history_not_persisted_on_failure(
        self, http_client: httpx.AsyncClient
    ):
        with (
            patch(_FAKE_DECOMPOSE, side_effect=_fake_decompose()),
            patch(_FAKE_SYNTHESIZE, self._failing_synthesize),
            patch(_FAKE_RETRIEVE, return_value=[]),
        ):
            await _stream_chat(http_client, {"message": "Vad gäller?"})

        # No done event means no session_id was given, but a session was created.
        # Verify it has empty history (append_turn was never called).
        # We check by looking for any session created during this test.
        engine = create_async_engine(_async_url(_DATABASE_URL))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as s:
            from sqlalchemy import select
            from shared.models.session import Session as SessionModel

            result = await s.execute(select(SessionModel))
            sessions = result.scalars().all()
        await engine.dispose()

        # The session was created (by get_or_create_session) but history is empty
        assert len(sessions) == 1
        assert sessions[0].history == []
