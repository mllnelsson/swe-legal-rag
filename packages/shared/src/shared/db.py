import asyncio
import re
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.models.base import Base

__all__ = [
    "Base",
    "dispose_async_engine",
    "get_engine",
    "get_session",
    "get_async_session",
]


def _sync_url(database_url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+psycopg://", database_url)


def _async_url(database_url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", database_url)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        _sync_url(get_settings().database.database_url),
        # Deliberate: workers hold pooled connections across long idle stretches
        # between messages, and Postgres or anything in front of it may drop one
        # in the meantime. Pre-ping trades a round trip for not handing out a
        # dead connection.
        pool_pre_ping=True,
    )


@contextmanager
def get_session() -> Generator[Session, None, None]:
    engine = get_engine()
    with Session(engine) as session:
        yield session


_async_engines: dict[asyncio.AbstractEventLoop, AsyncEngine] = {}
_async_session_factories: dict[
    asyncio.AbstractEventLoop, async_sessionmaker[AsyncSession]
] = {}


def _get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """The session factory belonging to the running event loop.

    Keyed by loop because an asyncpg connection belongs to the loop that opened
    it: handing a pooled one to a second `asyncio.run` fails with "got Future
    attached to a different loop". Workers run one loop per message, so each
    message gets its own engine and must dispose it — see
    :func:`dispose_async_engine`. A process with one long-lived loop (the API
    server) keeps a single engine and its pool, exactly as before.
    """
    loop = asyncio.get_running_loop()
    factory = _async_session_factories.get(loop)
    if factory is None:
        engine = create_async_engine(_async_url(get_settings().database.database_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        _async_engines[loop] = engine
        _async_session_factories[loop] = factory
    return factory


async def dispose_async_engine() -> None:
    """Close the running loop's engine and the connections it pooled.

    Any caller that owns a loop for one unit of work must call this before the
    loop closes. Skipping it leaks a connection per message, which over a
    backfill reaches Postgres' connection limit.
    """
    loop = asyncio.get_running_loop()
    _async_session_factories.pop(loop, None)
    engine = _async_engines.pop(loop, None)
    if engine is not None:
        await engine.dispose()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
