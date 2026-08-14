from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.session_service import (
    append_turn,
    get_or_create_session,
    history_for_llm,
)
from shared.dtos.session import SessionRead


def _make_session(history: list[dict] | None = None) -> SessionRead:
    now = datetime.now(timezone.utc)
    return SessionRead(
        id=uuid.uuid4(),
        created_at=now,
        last_active_at=now,
        history=history or [],
    )


@pytest.fixture
def repo() -> Iterator[MagicMock]:
    """Patch the injected `session` repo namespace with async-mocked functions."""
    with patch("api.services.session_service.session_repo") as mock:
        mock.get_by_id = AsyncMock(return_value=None)
        mock.create = AsyncMock(return_value=_make_session())
        mock.update = AsyncMock(return_value=None)
        mock.append_history = AsyncMock(return_value=None)
        yield mock


# Sentinel standing in for the AsyncSession handle threaded to the repo functions.
db = MagicMock()


class TestGetOrCreateSession:
    @pytest.mark.asyncio
    async def test_none_session_id_creates_new_session(self, repo: MagicMock):
        result = await get_or_create_session(None, db)
        repo.create.assert_called_once()
        repo.get_by_id.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_known_session_id_loads_existing(self, repo: MagicMock):
        session = _make_session(history=[{"role": "user", "content": "Hej"}])
        repo.get_by_id.return_value = session
        result = await get_or_create_session(session.id, db)
        repo.get_by_id.assert_called_once_with(db, session.id)
        repo.create.assert_not_called()
        assert result.id == session.id

    @pytest.mark.asyncio
    async def test_stale_session_id_creates_new_session(self, repo: MagicMock):
        stale_id = uuid.uuid4()
        repo.get_by_id.return_value = None
        result = await get_or_create_session(stale_id, db)
        repo.get_by_id.assert_called_once_with(db, stale_id)
        repo.create.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_valid_session_id_returns_with_history(self, repo: MagicMock):
        history = [
            {"role": "user", "content": "Vad gäller?"},
            {"role": "assistant", "content": "Kyrkorätten säger..."},
        ]
        session = _make_session(history=history)
        repo.get_by_id.return_value = session
        result = await get_or_create_session(session.id, db)
        assert result.history == history


INTERACTION_ID = "11111111-1111-4111-8111-111111111111"


class TestAppendTurn:
    @pytest.mark.asyncio
    async def test_appends_user_and_assistant_entries(self, repo: MagicMock):
        session = _make_session(history=[])
        await append_turn(
            session.id,
            "Vad gäller?",
            "Kyrkorätten säger...",
            db,
            interaction_id=INTERACTION_ID,
        )
        repo.append_history.assert_called_once()
        entries = repo.append_history.call_args.args[2]
        assert entries == [
            {
                "role": "user",
                "content": "Vad gäller?",
                "interaction_id": INTERACTION_ID,
            },
            {
                "role": "assistant",
                "content": "Kyrkorätten säger...",
                "interaction_id": INTERACTION_ID,
            },
        ]

    @pytest.mark.asyncio
    async def test_both_entries_carry_the_same_interaction_id(self, repo: MagicMock):
        """The turn is the unit a trace lookup resolves, not the message."""
        session = _make_session(history=[])
        await append_turn(session.id, "q", "a", db, interaction_id=INTERACTION_ID)
        entries = repo.append_history.call_args.args[2]
        assert [entry["interaction_id"] for entry in entries] == [
            INTERACTION_ID,
            INTERACTION_ID,
        ]

    @pytest.mark.asyncio
    async def test_existing_history_is_never_read(self, repo: MagicMock):
        """Reading it to append is what loses a concurrent turn.

        Postgres does the append; nothing here needs to know what is already
        stored, so the only entries handed over are the new ones.
        """
        session = _make_session(history=[{"role": "user", "content": "Tidigare"}])
        await append_turn(session.id, "q", "a", db, interaction_id=INTERACTION_ID)

        repo.get_by_id.assert_not_called()
        assert len(repo.append_history.call_args.args[2]) == 2

    @pytest.mark.asyncio
    async def test_updates_last_active_at(self, repo: MagicMock):
        session = _make_session()
        await append_turn(session.id, "q", "a", db, interaction_id=INTERACTION_ID)
        assert repo.append_history.call_args.args[3] is not None

    @pytest.mark.asyncio
    async def test_missing_session_is_left_to_the_update(self, repo: MagicMock):
        """`WHERE id = …` matches no row, so no pre-check is needed."""
        await append_turn(uuid.uuid4(), "q", "a", db, interaction_id=INTERACTION_ID)
        repo.get_by_id.assert_not_called()
        repo.append_history.assert_called_once()


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

    def test_strips_bookkeeping_fields_from_stored_entries(self):
        """No stored field reaches a prompt except role and content.

        `ai.synthesize_answer` renders the history with `json.dumps` over whole
        entries, so anything left on one is sent to the model — and re-sent on
        every later turn.
        """
        session = _make_session(
            history=[
                {"role": "user", "content": "q", "interaction_id": INTERACTION_ID},
                {"role": "assistant", "content": "a", "interaction_id": INTERACTION_ID},
            ]
        )
        result = history_for_llm(session, max_turns=5)
        assert result == [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]

    def test_tolerates_entries_written_before_interaction_ids(self):
        """The column is untyped JSONB; older rows have no interaction_id."""
        session = _make_session(history=[{"role": "user", "content": "q"}])
        assert history_for_llm(session, max_turns=5) == [
            {"role": "user", "content": "q"}
        ]
