"""The session history append, against a real Postgres.

Only Postgres can prove this one. The bug being guarded against is a lost
update: two turns of the same conversation finishing at the same time, each
reading the history array, appending to it, and writing the whole thing back —
so whichever commits second erases the other. A mock session cannot show it,
because the interleaving is the defect.
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
