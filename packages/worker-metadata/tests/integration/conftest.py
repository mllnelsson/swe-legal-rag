from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.task import TaskCreate
from shared.models import Base  # noqa: F401 - registers all models with Base.metadata
from shared.queue.base import QueueMessage
from shared.queue.sync import SyncQueueBroker, SyncQueuePublisher
from shared.repositories import (
    document,
    task,
)

_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/overklagan"
)

_SWEDISH_TEXT = (
    "ÖN 2023-0042\n\n"
    "Beslut den 15 januari 2023\n\n"
    "Ärende: Kyrkogårdsförvaltning\n\n"
    "Överklagandenämnden bifaller överklagandet och upphäver det överklagade beslutet."
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
def document_repo(session: AsyncSession):
    return document


@pytest.fixture
def task_repo(session: AsyncSession):
    return task


@pytest.fixture
def published_messages() -> list[QueueMessage]:
    return []


@pytest.fixture
def sync_publisher(published_messages: list[QueueMessage]) -> SyncQueuePublisher:
    broker = SyncQueueBroker()
    broker.register("extract", lambda msg: published_messages.append(msg))
    return SyncQueuePublisher(broker)


@pytest.fixture
async def test_document(session: AsyncSession, document_repo):
    doc = await document_repo.create(
        session, DocumentCreate(source_url="https://example.com/decision.pdf")
    )
    await document_repo.update(session, doc.id, DocumentUpdate(raw_text=_SWEDISH_TEXT))
    await session.commit()
    return await document_repo.get_by_id(session, doc.id)


@pytest.fixture
async def metadata_task(session: AsyncSession, task_repo, test_document):
    task = await task_repo.create(
        session,
        TaskCreate(document_id=test_document.id, step="metadata", status="pending"),
    )
    await session.commit()
    return task
