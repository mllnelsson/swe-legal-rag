from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.models import Base  # noqa: F401 — registers all ORM models
from shared.repositories import (
    chunk,
    document,
    document_entity,
    document_reference,
    entity,
    search,
)
from shared.testing import bind_repo

_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/overklagan"
)


def _sync_url(url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+psycopg://", url)


def _async_url(url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", url)


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(_sync_url(_DATABASE_URL))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
async def session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    with db_engine.connect() as conn:
        conn.execute(text("TRUNCATE documents CASCADE"))
        conn.commit()

    engine = create_async_engine(_async_url(_DATABASE_URL))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def truncate_sessions(db_engine):
    with db_engine.connect() as conn:
        conn.execute(text("TRUNCATE sessions"))
        conn.commit()


@pytest.fixture
def document_repo(session: AsyncSession):
    return bind_repo(document, session)


@pytest.fixture
def chunk_repo(session: AsyncSession):
    return bind_repo(chunk, session)


@pytest.fixture
def search_repo(session: AsyncSession):
    return bind_repo(search, session)


@pytest.fixture
def entity_repo(session: AsyncSession):
    return bind_repo(entity, session)


@pytest.fixture
def doc_entity_repo(session: AsyncSession):
    return bind_repo(document_entity, session)


@pytest.fixture
def doc_ref_repo(session: AsyncSession):
    return bind_repo(document_reference, session)
