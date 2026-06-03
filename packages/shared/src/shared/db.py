import os
import re
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from shared.models.base import Base

__all__ = ["Base", "get_engine", "get_session", "get_async_session"]


def _sync_url(database_url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+psycopg://", database_url)


def _async_url(database_url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", database_url)


def get_engine() -> Engine:
    return create_engine(_sync_url(os.environ["DATABASE_URL"]))


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
        _async_engine = create_async_engine(_async_url(os.environ["DATABASE_URL"]))
        _async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)
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
