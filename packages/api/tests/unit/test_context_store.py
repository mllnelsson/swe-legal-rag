"""The Postgres-backed context store's id handling, without a database.

The SQL is exercised against a real Postgres in the session-repo integration
tests; here we only pin the store's own contract: it keys on a session id string,
and an id that is not a UUID belongs to no row, so it reads empty and writes
nothing rather than raising into the middle of a chat turn.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from api.services import context_store as module
from api.services.context_store import PostgresContextStore


class _RecordingRepo:
    def __init__(self) -> None:
        self.got: list[uuid.UUID] = []
        self.set_calls: list[tuple[uuid.UUID, dict]] = []

    async def get_context(self, db: object, session_id: uuid.UUID) -> dict:
        self.got.append(session_id)
        return {"cases_discussed": ["12/2024"]}

    async def set_context(
        self, db: object, session_id: uuid.UUID, context: dict
    ) -> None:
        self.set_calls.append((session_id, context))


def _store(monkeypatch) -> tuple[PostgresContextStore, _RecordingRepo]:
    repo = _RecordingRepo()
    monkeypatch.setattr(module, "session_repo", repo)
    # The db is never touched — the mocked repo stands in for every query.
    return PostgresContextStore(db=cast(AsyncSession, object())), repo


async def test_a_valid_id_delegates_to_the_repo(monkeypatch) -> None:
    store, repo = _store(monkeypatch)
    session_id = uuid.uuid4()

    got = await store.get(str(session_id))
    await store.set(str(session_id), {"cases_discussed": ["7/2022"]})

    assert got == {"cases_discussed": ["12/2024"]}
    assert repo.got == [session_id]
    assert repo.set_calls == [(session_id, {"cases_discussed": ["7/2022"]})]


async def test_a_non_uuid_id_reads_empty_and_writes_nothing(monkeypatch) -> None:
    store, repo = _store(monkeypatch)

    assert await store.get("not-a-uuid") == {}
    await store.set("not-a-uuid", {"x": 1})

    assert repo.got == []
    assert repo.set_calls == []
