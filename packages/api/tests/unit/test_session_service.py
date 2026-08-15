from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.session_service import (
    TITLE_MAX_CHARS,
    UNTITLED,
    append_turn,
    delete_session,
    get_or_create_session,
    get_transcript,
    history_for_llm,
    list_sessions,
    session_title,
    transcript_turns,
)
from shared.dtos.session import SessionRead, SessionSummaryRow


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
        mock.list_summaries = AsyncMock(return_value=[])
        mock.count_with_history = AsyncMock(return_value=0)
        mock.delete = AsyncMock(return_value=True)
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


class TestSessionTitle:
    def test_short_question_is_used_verbatim(self):
        assert session_title("Vad gäller vid jäv?") == "Vad gäller vid jäv?"

    def test_whitespace_is_collapsed(self):
        assert session_title("  Vad\n gäller\tvid  jäv? ") == "Vad gäller vid jäv?"

    def test_empty_first_message_falls_back(self):
        assert session_title("") == UNTITLED
        assert session_title("   ") == UNTITLED

    def test_missing_first_message_falls_back(self):
        """`history -> 0 ->> 'content'` is NULL for an entry with no content."""
        assert session_title(None) == UNTITLED

    def test_exactly_at_the_limit_is_not_truncated(self):
        question = "a" * TITLE_MAX_CHARS
        assert session_title(question) == question

    def test_long_question_is_cut_on_a_word_boundary(self):
        question = "Vilka beslut har nämnden fattat om jäv i kyrkoråd " + (
            "under de senaste åren?"
        )
        title = session_title(question)

        assert title.endswith("…")
        assert len(title) <= TITLE_MAX_CHARS + 1
        # The user's own words, unaltered up to the cut — nothing paraphrased.
        assert question.startswith(title.removesuffix("…"))
        assert not title.removesuffix("…").endswith(" ")

    def test_a_single_long_word_is_cut_where_it_is(self):
        """No word boundary to break on; better a hard cut than no title."""
        title = session_title("x" * (TITLE_MAX_CHARS + 20))
        assert title == "x" * TITLE_MAX_CHARS + "…"


class TestTranscriptTurns:
    def test_pairs_a_stored_turn(self):
        turns = transcript_turns(
            [
                {"role": "user", "content": "Vad gäller?", "interaction_id": "i1"},
                {
                    "role": "assistant",
                    "content": "Detta gäller.",
                    "interaction_id": "i1",
                },
            ]
        )
        assert len(turns) == 1
        assert turns[0].question == "Vad gäller?"
        assert turns[0].answer == "Detta gäller."
        assert turns[0].interaction_id == "i1"

    def test_pairs_several_turns_in_order(self):
        history = []
        for i in range(3):
            history.append({"role": "user", "content": f"q{i}"})
            history.append({"role": "assistant", "content": f"a{i}"})

        turns = transcript_turns(history)
        assert [t.question for t in turns] == ["q0", "q1", "q2"]
        assert [t.answer for t in turns] == ["a0", "a1", "a2"]

    def test_empty_history_has_no_turns(self):
        assert transcript_turns([]) == []

    def test_unpaired_trailing_question_still_renders(self):
        """The pairing is a convention `append_turn` keeps, not a constraint."""
        turns = transcript_turns(
            [
                {"role": "user", "content": "q0"},
                {"role": "assistant", "content": "a0"},
                {"role": "user", "content": "q1"},
            ]
        )
        assert len(turns) == 2
        assert turns[1].question == "q1"
        assert turns[1].answer == ""

    def test_answer_without_a_question_still_renders(self):
        turns = transcript_turns([{"role": "assistant", "content": "a"}])
        assert len(turns) == 1
        assert turns[0].question == ""
        assert turns[0].answer == "a"

    def test_missing_interaction_id_is_none(self):
        """Entries written before the field existed carry no id."""
        turns = transcript_turns(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
            ]
        )
        assert turns[0].interaction_id is None

    def test_non_string_content_does_not_raise(self):
        """JSONB is untyped; a malformed row is a display problem, not a 500."""
        turns = transcript_turns([{"role": "user", "content": {"oops": 1}}])
        assert turns[0].question == ""


def _summary_row(
    *,
    first_message: str | None = "Vad gäller?",
    entry_count: int = 2,
) -> SessionSummaryRow:
    now = datetime.now(timezone.utc)
    return SessionSummaryRow(
        id=uuid.uuid4(),
        created_at=now,
        last_active_at=now,
        first_message=first_message,
        entry_count=entry_count,
    )


class TestListSessions:
    @pytest.mark.asyncio
    async def test_titles_each_row_and_carries_the_total(self, repo: MagicMock):
        repo.list_summaries.return_value = [_summary_row(entry_count=4)]
        repo.count_with_history.return_value = 7

        page = await list_sessions(db, limit=10, offset=0)

        assert page.total == 7
        assert page.limit == 10
        assert page.offset == 0
        assert page.items[0].title == "Vad gäller?"
        assert page.items[0].turn_count == 2

    @pytest.mark.asyncio
    async def test_turn_count_rounds_an_unpaired_entry_up(self, repo: MagicMock):
        repo.list_summaries.return_value = [_summary_row(entry_count=3)]
        page = await list_sessions(db, limit=10, offset=0)
        assert page.items[0].turn_count == 2

    @pytest.mark.asyncio
    async def test_paging_is_passed_through(self, repo: MagicMock):
        await list_sessions(db, limit=5, offset=10)
        assert repo.list_summaries.call_args.kwargs == {"limit": 5, "offset": 10}


class TestGetTranscript:
    @pytest.mark.asyncio
    async def test_unknown_session_is_none(self, repo: MagicMock):
        repo.get_by_id.return_value = None
        assert await get_transcript(uuid.uuid4(), db) is None

    @pytest.mark.asyncio
    async def test_known_session_is_paired_into_turns(self, repo: MagicMock):
        session = _make_session(
            history=[
                {"role": "user", "content": "q", "interaction_id": INTERACTION_ID},
                {"role": "assistant", "content": "a", "interaction_id": INTERACTION_ID},
            ]
        )
        repo.get_by_id.return_value = session

        transcript = await get_transcript(session.id, db)

        assert transcript is not None
        assert transcript.id == session.id
        assert len(transcript.turns) == 1
        assert transcript.turns[0].interaction_id == INTERACTION_ID


class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_reports_what_the_repo_reports(self, repo: MagicMock):
        repo.delete.return_value = False
        assert await delete_session(uuid.uuid4(), db) is False

        repo.delete.return_value = True
        assert await delete_session(uuid.uuid4(), db) is True
