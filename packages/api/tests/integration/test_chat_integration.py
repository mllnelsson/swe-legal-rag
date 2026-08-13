from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agents.chat import DoneEvent, SourcesEvent, TokenEvent
from api.dependencies import get_db
from api.main import create_app
from shared.repositories import session as session_repo
from shared.testing import to_async_url


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
async def api_app(
    clean_database: None, test_database_url: str
) -> AsyncGenerator[Any, None]:
    engine = create_async_engine(to_async_url(test_database_url))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app()
    app.state.embedding_provider = MagicMock()
    app.state.storage = MagicMock()
    # The lifespan never runs under this fixture, so every provider the chat route
    # reads off app.state has to be placed here by hand.
    app.state.structured_llm_provider = MagicMock()
    app.state.chat_llm_provider = MagicMock()
    app.state.read_llm_provider = MagicMock()
    app.state.sql_llm_provider = MagicMock()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    yield app
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def http_client(api_app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="http://test",
    )


async def _load_session_from_db(database_url: str, session_id: uuid.UUID) -> Any:
    engine = create_async_engine(to_async_url(database_url))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        result = await session_repo.get_by_id(s, session_id)
    await engine.dispose()
    return result


def _agent_emitting(tokens: list[str]) -> Any:
    """Stands in for the whole agent: the route's job is the wire, not the loop.

    The loop itself is covered against a scripted provider in
    `packages/agents/tests/unit/test_chat_agent.py`. What only a real database
    can prove is what this file asserts: that a turn round-trips to the
    `sessions` table, and that a failed one does not.
    """

    async def _inner(request, toolset, **_kwargs) -> AsyncIterator[Any]:
        _CAPTURED_HISTORIES.append(list(request.history))
        for token in tokens:
            yield TokenEvent(text=token)
        yield SourcesEvent(sources=[])
        yield DoneEvent()

    return _inner


_CAPTURED_HISTORIES: list[list] = []

_FAKE_AGENT = "api.routes.chat.run_chat_agent"

_SWEDISH_TOKENS = ["Kyrkan ", "regleras ", "av kyrkoordningen."]


@pytest.fixture(autouse=True)
def _reset_captured_histories() -> None:
    _CAPTURED_HISTORIES.clear()


class TestNewSessionRoundTrip:
    async def test_events_in_order(self, http_client: httpx.AsyncClient):
        with patch(_FAKE_AGENT, _agent_emitting(_SWEDISH_TOKENS)):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        assert len([e for e in events if e["event"] == "token"]) == len(_SWEDISH_TOKENS)

        token_idxs = [i for i, e in enumerate(events) if e["event"] == "token"]
        sources_idx = next(i for i, e in enumerate(events) if e["event"] == "sources")
        done_idx = next(i for i, e in enumerate(events) if e["event"] == "done")

        assert max(token_idxs) < sources_idx < done_idx

    async def test_done_carries_session_id(self, http_client: httpx.AsyncClient):
        with patch(_FAKE_AGENT, _agent_emitting(_SWEDISH_TOKENS)):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        done = next(e for e in events if e["event"] == "done")
        assert uuid.UUID(done["data"]["session_id"])

    async def test_history_persisted_to_db(
        self, http_client: httpx.AsyncClient, test_database_url: str
    ):
        with patch(_FAKE_AGENT, _agent_emitting(_SWEDISH_TOKENS)):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        session_id = uuid.UUID(
            next(e for e in events if e["event"] == "done")["data"]["session_id"]
        )
        db_session = await _load_session_from_db(test_database_url, session_id)

        assert db_session is not None
        assert len(db_session.history) == 2
        assert db_session.history[0] == {"role": "user", "content": "Vad gäller?"}
        assert db_session.history[1]["role"] == "assistant"
        assert "kyrkoordningen" in db_session.history[1]["content"]


class TestFollowUpConversation:
    async def test_prior_history_reaches_the_agent(
        self, http_client: httpx.AsyncClient
    ):
        with patch(_FAKE_AGENT, _agent_emitting(_SWEDISH_TOKENS)):
            first = await _stream_chat(http_client, {"message": "Vad gäller?"})
            session_id = next(e for e in first if e["event"] == "done")["data"][
                "session_id"
            ]
            await _stream_chat(
                http_client, {"message": "Berätta mer", "session_id": session_id}
            )

        assert len(_CAPTURED_HISTORIES) == 2
        assert _CAPTURED_HISTORIES[0] == []
        second = _CAPTURED_HISTORIES[1]
        assert len(second) == 2
        assert second[0] == {"role": "user", "content": "Vad gäller?"}
        assert second[1]["role"] == "assistant"


class TestMidStreamFailure:
    """A failure after the headers are sent is an in-band event, not a status."""

    @staticmethod
    def _failing_agent():
        async def _inner(request, toolset, **_kwargs) -> AsyncIterator[Any]:
            yield TokenEvent(text="Partial ")
            raise RuntimeError("LLM provider failed")

        return _inner

    async def test_error_event_emitted(self, http_client: httpx.AsyncClient):
        with patch(_FAKE_AGENT, self._failing_agent()):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) == 1
        assert "message" in error_events[0]["data"]

    async def test_no_done_after_error(self, http_client: httpx.AsyncClient):
        with patch(_FAKE_AGENT, self._failing_agent()):
            events = await _stream_chat(http_client, {"message": "Vad gäller?"})

        assert not any(e["event"] == "done" for e in events)

    async def test_history_not_persisted_on_failure(
        self, http_client: httpx.AsyncClient, test_database_url: str
    ):
        with patch(_FAKE_AGENT, self._failing_agent()):
            await _stream_chat(http_client, {"message": "Vad gäller?"})

        # The session was created by get_or_create_session, but the failed turn
        # was never appended to it.
        engine = create_async_engine(to_async_url(test_database_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as s:
            from shared.models.session import Session as SessionModel
            from sqlalchemy import select

            result = await s.execute(select(SessionModel))
            sessions = result.scalars().all()
        await engine.dispose()

        assert len(sessions) == 1
        assert sessions[0].history == []
