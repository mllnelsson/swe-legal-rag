"""A `ContextStore` backed by the `sessions.context` column.

This is the durable implementation of agent-kit's `ContextStore` protocol for
this app: the carry-over blob lives in Postgres, keyed by the chat session's id,
beside the transcript in the same row. It reads and writes through the same
request-scoped `AsyncSession` the rest of the turn uses, so the blob a turn
writes is committed with that turn's history, in one transaction — see
`shared.repositories.session.set_context`.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from agent_kit import JsonBlob
from shared.repositories import session as session_repo

logger = logging.getLogger(__name__)


class PostgresContextStore:
    """Reads and writes a conversation's carry-over blob in `sessions.context`.

    Keyed by the session id as a string, the shape agent-kit passes. An id that
    is not a UUID belongs to no row here, so `get` returns `{}` and `set` is a
    no-op — the same as an unknown session — rather than raising into the turn.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, conversation_id: str) -> JsonBlob:
        session_id = _as_uuid(conversation_id)
        if session_id is None:
            return {}
        return await session_repo.get_context(self._db, session_id)

    async def set(self, conversation_id: str, blob: JsonBlob) -> None:
        session_id = _as_uuid(conversation_id)
        if session_id is None:
            return
        await session_repo.set_context(self._db, session_id, blob)


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        logger.debug("context store ignoring non-uuid conversation id %r", value)
        return None
