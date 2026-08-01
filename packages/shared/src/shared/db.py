import re
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.models.base import Base

__all__ = ["Base", "get_engine", "get_session", "get_async_session"]


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


_async_engine = None
_async_session_factory = None


def _get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_engine, _async_session_factory
    if _async_session_factory is None:
        _async_engine = create_async_engine(
            _async_url(get_settings().database.database_url)
        )
        _async_session_factory = async_sessionmaker(
            _async_engine, expire_on_commit=False
        )
    return _async_session_factory


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
