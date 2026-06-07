import os
import re
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.models import Base  # noqa: F401 - registers all models with Base.metadata
from shared.queue.base import QueueMessage
from shared.queue.sync import SyncQueueBroker, SyncQueuePublisher
from shared.repositories.document import DocumentRepository
from shared.repositories.task import TaskRepository
from shared.storage.local import LocalStorageBackend

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
def document_repo(session: AsyncSession) -> DocumentRepository:
    return DocumentRepository(session)


@pytest.fixture
def task_repo(session: AsyncSession) -> TaskRepository:
    return TaskRepository(session)


@pytest.fixture
def local_storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(tmp_path)


@pytest.fixture
def published_messages() -> list[QueueMessage]:
    return []


@pytest.fixture
def sync_publisher(published_messages: list[QueueMessage]) -> SyncQueuePublisher:
    broker = SyncQueueBroker()
    broker.register("metadata", lambda msg: published_messages.append(msg))
    return SyncQueuePublisher(broker)
