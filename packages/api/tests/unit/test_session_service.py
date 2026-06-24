from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from api.services.session_service import append_turn, get_or_create_session, history_for_llm
from shared.dtos.session import SessionRead


def _make_session(history: list[dict] | None = None) -> SessionRead:
    now = datetime.now(timezone.utc)
    return SessionRead(
        id=uuid.uuid4(),
        created_at=now,
        last_active_at=now,
        history=history or [],
    )


def _make_repo(existing: SessionRead | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id.return_value = existing
    repo.create.return_value = _make_session()
    repo.update.return_value = existing
    return repo


class TestGetOrCreateSession:
    @pytest.mark.asyncio
    async def test_none_session_id_creates_new_session(self):
        repo = _make_repo(existing=None)
        result = await get_or_create_session(None, repo)
        repo.create.assert_called_once()
        repo.get_by_id.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_known_session_id_loads_existing(self):
        session = _make_session(history=[{"role": "user", "content": "Hej"}])
        repo = _make_repo(existing=session)
        result = await get_or_create_session(session.id, repo)
        repo.get_by_id.assert_called_once_with(session.id)
        repo.create.assert_not_called()
        assert result.id == session.id

    @pytest.mark.asyncio
    async def test_stale_session_id_creates_new_session(self):
        stale_id = uuid.uuid4()
        repo = _make_repo(existing=None)
        result = await get_or_create_session(stale_id, repo)
        repo.get_by_id.assert_called_once_with(stale_id)
        repo.create.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_valid_session_id_returns_with_history(self):
        history = [
            {"role": "user", "content": "Vad gäller?"},
            {"role": "assistant", "content": "Kyrkorätten säger..."},
        ]
        session = _make_session(history=history)
        repo = _make_repo(existing=session)
        result = await get_or_create_session(session.id, repo)
        assert result.history == history


class TestAppendTurn:
    @pytest.mark.asyncio
    async def test_appends_user_and_assistant_entries(self):
        session = _make_session(history=[])
        repo = _make_repo(existing=session)
        await append_turn(session.id, "Vad gäller?", "Kyrkorätten säger...", repo)
        repo.update.assert_called_once()
        call_args = repo.update.call_args
        update_dto = call_args.args[1]
        assert {"role": "user", "content": "Vad gäller?"} in update_dto.history
        assert {"role": "assistant", "content": "Kyrkorätten säger..."} in update_dto.history

    @pytest.mark.asyncio
    async def test_preserves_existing_history(self):
        prior = [{"role": "user", "content": "Tidigare fråga"}, {"role": "assistant", "content": "Svar"}]
        session = _make_session(history=prior)
        repo = _make_repo(existing=session)
        await append_turn(session.id, "Ny fråga", "Nytt svar", repo)
        update_dto = repo.update.call_args.args[1]
        assert len(update_dto.history) == 4
        assert update_dto.history[0] == prior[0]

    @pytest.mark.asyncio
    async def test_updates_last_active_at(self):
        session = _make_session()
        repo = _make_repo(existing=session)
        await append_turn(session.id, "q", "a", repo)
        update_dto = repo.update.call_args.args[1]
        assert update_dto.last_active_at is not None

    @pytest.mark.asyncio
    async def test_no_op_when_session_not_found(self):
        repo = _make_repo(existing=None)
        await append_turn(uuid.uuid4(), "q", "a", repo)
        repo.update.assert_not_called()


class TestHistoryForLlm:
    def test_returns_all_when_under_limit(self):
        history = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]
        session = _make_session(history=history)
        result = history_for_llm(session, max_turns=10)
        assert result == history

    def test_truncates_to_last_n_turns(self):
        history = []
        for i in range(6):
            history.append({"role": "user", "content": f"q{i}"})
            history.append({"role": "assistant", "content": f"a{i}"})
        session = _make_session(history=history)
        result = history_for_llm(session, max_turns=2)
        assert len(result) == 4
        assert result[0] == {"role": "user", "content": "q4"}
        assert result[-1] == {"role": "assistant", "content": "a5"}

    def test_empty_history_returns_empty(self):
        session = _make_session(history=[])
        result = history_for_llm(session, max_turns=5)
        assert result == []

    def test_exactly_at_limit_returns_all(self):
        history = []
        for i in range(3):
            history.append({"role": "user", "content": f"q{i}"})
            history.append({"role": "assistant", "content": f"a{i}"})
        session = _make_session(history=history)
        result = history_for_llm(session, max_turns=3)
        assert len(result) == 6
