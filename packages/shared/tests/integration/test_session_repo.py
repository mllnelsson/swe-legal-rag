"""The session history append and the conversation list, against a real Postgres.

Only Postgres can prove either. The append guards against a lost update: two
turns of the same conversation finishing at the same time, each reading the
history array, appending to it, and writing the whole thing back — so whichever
commits second erases the other. A mock session cannot show it, because the
interleaving is the defect.

The list is here for the same reason in a quieter form: `list_summaries` does
its work in SQL — `jsonb_extract_path_text` for the title, `jsonb_array_length`
for the size and the empty-history filter — so what it returns is a claim about
Postgres, not about Python.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.dtos.session import SessionCreate
from shared.repositories import session as session_repo
from shared.testing import to_async_url


def _turn(marker: str) -> list[dict]:
    return [
        {"role": "user", "content": f"q{marker}", "interaction_id": marker},
        {"role": "assistant", "content": f"a{marker}", "interaction_id": marker},
    ]


@pytest.fixture
async def second_session(
    test_database_url: str,
) -> AsyncGenerator[AsyncSession, None]:
    """A second connection, so two turns can genuinely overlap.

    The shared `session` fixture yields one connection; a lost update needs two
    transactions in flight at once.
    """
    engine = create_async_engine(to_async_url(test_database_url))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as open_session:
        yield open_session
    await engine.dispose()


class TestAppendHistory:
    async def test_appends_to_an_empty_history(self, session: AsyncSession):
        created = await session_repo.create(session, SessionCreate())

        await session_repo.append_history(
            session, created.id, _turn("one"), datetime.now(UTC)
        )
        await session.commit()

        stored = await session_repo.get_by_id(session, created.id)
        assert stored is not None
        assert [entry["content"] for entry in stored.history] == ["qone", "aone"]

    async def test_appends_after_existing_entries(self, session: AsyncSession):
        created = await session_repo.create(session, SessionCreate())
        await session_repo.append_history(
            session, created.id, _turn("one"), datetime.now(UTC)
        )
        await session_repo.append_history(
            session, created.id, _turn("two"), datetime.now(UTC)
        )
        await session.commit()

        stored = await session_repo.get_by_id(session, created.id)
        assert stored is not None
        assert [entry["interaction_id"] for entry in stored.history] == [
            "one",
            "one",
            "two",
            "two",
        ]

    async def test_moves_last_active_at(self, session: AsyncSession):
        created = await session_repo.create(session, SessionCreate())
        moment = datetime(2026, 8, 14, 10, 15, 33, tzinfo=UTC)

        await session_repo.append_history(session, created.id, _turn("one"), moment)
        await session.commit()

        stored = await session_repo.get_by_id(session, created.id)
        assert stored is not None
        assert stored.last_active_at == moment

    async def test_a_missing_session_is_a_no_op(self, session: AsyncSession):
        """No pre-read: the UPDATE simply matches no row."""
        await session_repo.append_history(
            session, uuid.uuid4(), _turn("one"), datetime.now(UTC)
        )
        await session.commit()

    async def test_concurrent_turns_do_not_lose_each_other(
        self, session: AsyncSession, second_session: AsyncSession
    ):
        """The regression this function exists for.

        The barrier is what makes this deterministic rather than a race the test
        usually wins. Both connections load the session first — which is exactly
        what each chat request does at its start — and only then does either
        append. An implementation that reads the array and writes it back sees a
        stale copy at that point and keeps only one of the two turns; appending
        in SQL is applied to whatever the row holds when the lock is released.
        """
        created = await session_repo.create(session, SessionCreate())
        await session.commit()

        both_have_read = asyncio.Barrier(2)

        async def append(connection: AsyncSession, marker: str) -> None:
            await session_repo.get_by_id(connection, created.id)
            await both_have_read.wait()
            await session_repo.append_history(
                connection, created.id, _turn(marker), datetime.now(UTC)
            )
            await connection.commit()

        await asyncio.gather(
            append(session, "one"),
            append(second_session, "two"),
        )

        stored = await session_repo.get_by_id(second_session, created.id)
        assert stored is not None
        assert len(stored.history) == 4
        assert {entry["interaction_id"] for entry in stored.history} == {"one", "two"}


async def _conversation(
    session: AsyncSession, question: str, *, active_at: datetime, turns: int = 1
) -> uuid.UUID:
    """A session that actually held a conversation."""
    created = await session_repo.create(session, SessionCreate())
    entries = [
        {"role": "user", "content": question, "interaction_id": "i"},
        {"role": "assistant", "content": "svar", "interaction_id": "i"},
    ] * turns
    await session_repo.append_history(session, created.id, entries, active_at)
    await session.commit()
    return created.id


class TestListSummaries:
    async def test_titles_a_conversation_by_its_first_question(
        self, session: AsyncSession
    ):
        await _conversation(session, "Vad gäller vid jäv?", active_at=datetime.now(UTC))

        rows = await session_repo.list_summaries(session, limit=10, offset=0)

        assert len(rows) == 1
        assert rows[0].first_message == "Vad gäller vid jäv?"
        assert rows[0].entry_count == 2

    async def test_counts_every_entry_not_every_turn(self, session: AsyncSession):
        """The projection reports what is stored; pairing is the service's job."""
        await _conversation(session, "q", active_at=datetime.now(UTC), turns=3)

        rows = await session_repo.list_summaries(session, limit=10, offset=0)
        assert rows[0].entry_count == 6

    async def test_orders_by_most_recently_active(self, session: AsyncSession):
        older = datetime(2026, 8, 1, tzinfo=UTC)
        newer = datetime(2026, 8, 14, tzinfo=UTC)
        await _conversation(session, "äldre", active_at=older)
        await _conversation(session, "nyare", active_at=newer)

        rows = await session_repo.list_summaries(session, limit=10, offset=0)
        assert [row.first_message for row in rows] == ["nyare", "äldre"]

    async def test_a_session_that_never_held_a_turn_is_absent(
        self, session: AsyncSession
    ):
        """The load-bearing filter.

        A session row is created before the agent runs, so every failed, aborted
        or rejected request leaves one behind with an empty history. Those are
        not conversations, and without this the list fills with untitled blanks.
        """
        await session_repo.create(session, SessionCreate())
        await _conversation(session, "riktig fråga", active_at=datetime.now(UTC))
        await session.commit()

        rows = await session_repo.list_summaries(session, limit=10, offset=0)
        assert [row.first_message for row in rows] == ["riktig fråga"]

    async def test_paging(self, session: AsyncSession):
        for day in range(1, 4):
            await _conversation(
                session, f"q{day}", active_at=datetime(2026, 8, day, tzinfo=UTC)
            )

        page = await session_repo.list_summaries(session, limit=1, offset=1)
        assert [row.first_message for row in page] == ["q2"]

    async def test_swedish_survives_the_projection(self, session: AsyncSession):
        """`jsonb_extract_path_text` returns text, not a quoted JSON scalar."""
        await _conversation(
            session, "Överklagande om åtgärd", active_at=datetime.now(UTC)
        )

        rows = await session_repo.list_summaries(session, limit=10, offset=0)
        assert rows[0].first_message == "Överklagande om åtgärd"


class TestCountWithHistory:
    async def test_counts_only_real_conversations(self, session: AsyncSession):
        await session_repo.create(session, SessionCreate())
        await _conversation(session, "q1", active_at=datetime.now(UTC))
        await _conversation(session, "q2", active_at=datetime.now(UTC))
        await session.commit()

        assert await session_repo.count_with_history(session) == 2

    async def test_no_sessions_is_zero(self, session: AsyncSession):
        assert await session_repo.count_with_history(session) == 0


class TestDelete:
    async def test_removes_the_conversation(self, session: AsyncSession):
        session_id = await _conversation(session, "q", active_at=datetime.now(UTC))

        assert await session_repo.delete(session, session_id) is True
        await session.commit()

        assert await session_repo.get_by_id(session, session_id) is None

    async def test_missing_session_reports_false(self, session: AsyncSession):
        """A delete that removed nothing must not read as a delete that did."""
        assert await session_repo.delete(session, uuid.uuid4()) is False
