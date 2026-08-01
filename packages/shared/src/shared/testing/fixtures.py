"""Pytest fixtures shared by every integration suite.

Registered globally as a plugin by the repo-root `conftest.py`, so a package's
own `tests/integration/conftest.py` only declares what is genuinely local to it:
its extra fixtures, its queue topic, its sample data.

The database these run against is never the development database — see
`shared.testing.database.resolve_test_database_url`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.models import Base  # noqa: F401 — registers all ORM models
from shared.queue.base import QueueMessage
from shared.queue.sync import SyncQueueBroker, SyncQueuePublisher
from shared.repositories import (
    chunk,
    document,
    document_entity,
    document_reference,
    entity,
    search,
    task,
    unresolved_reference,
)
from shared.storage.local import LocalStorageBackend
from shared.testing.database import (
    DEV_DATABASE_URL_DEFAULT,
    IntegrationDatabaseError,
    resolve_test_database_url,
    to_async_url,
    to_sync_url,
)

# `alembic.ini` and the `alembic/` script directory live at the repository root,
# four parents up from `packages/shared/src/shared/testing/`.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def _test_database_url() -> str:
    dev_url = os.environ.get("DATABASE_URL", DEV_DATABASE_URL_DEFAULT)
    try:
        return resolve_test_database_url(dev_url, os.environ.get("TEST_DATABASE_URL"))
    except IntegrationDatabaseError as exc:
        # Fail the run at the boundary rather than propagating a domain error
        # into pytest's fixture machinery, where it reads as a crash.
        raise pytest.UsageError(str(exc)) from exc


def check_test_database_is_not_the_development_one() -> None:
    """Abort the run now if the configured test database is the dev one.

    Called from the root conftest at collection so the failure is one message
    rather than an identical error attached to every test.
    """
    _test_database_url()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _test_database_url()


@pytest.fixture(scope="session")
def db_engine(test_database_url: str) -> Iterator[Engine]:
    """A migrated test database, one per test session.

    Schema comes from alembic rather than `Base.metadata.create_all()` so the
    tests see the same schema production does — including what the migrations
    alter after creating it.
    """
    sync_url = to_sync_url(test_database_url)
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    config.cmd_opts = None
    config.attributes["db_url"] = sync_url
    command.upgrade(config, "head")

    engine = create_engine(sync_url)
    yield engine
    engine.dispose()


def truncate_all_tables(engine: Engine) -> None:
    """Empty every application table so a test starts from a known state."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        conn.commit()


@pytest.fixture
def clean_database(db_engine: Engine) -> None:
    """Empty the database for a test that drives the app rather than a session."""
    truncate_all_tables(db_engine)


@pytest.fixture
async def session(
    db_engine: Engine, test_database_url: str
) -> AsyncGenerator[AsyncSession, None]:
    truncate_all_tables(db_engine)
    engine = create_async_engine(to_async_url(test_database_url))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as open_session:
        yield open_session
    await engine.dispose()


# Repositories are modules of functions taking the session first, and that is how
# production injects them. The fixtures hand back the module unchanged so a test
# calls exactly what a worker calls: `await document_repo.create(session, dto)`.


@pytest.fixture
def document_repo():
    return document


@pytest.fixture
def chunk_repo():
    return chunk


@pytest.fixture
def task_repo():
    return task


@pytest.fixture
def entity_repo():
    return entity


@pytest.fixture
def doc_entity_repo():
    return document_entity


@pytest.fixture
def doc_ref_repo():
    return document_reference


@pytest.fixture
def ref_repo():
    return document_reference


@pytest.fixture
def unresolved_repo():
    return unresolved_reference


@pytest.fixture
def search_repo():
    return search


@pytest.fixture
def local_storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(tmp_path)


@pytest.fixture
def published_messages() -> list[QueueMessage]:
    return []


@pytest.fixture
def next_topic() -> str:
    """The topic a worker publishes to when it finishes.

    Overridden in each worker package's `tests/integration/conftest.py`; the
    recording publisher below is otherwise identical everywhere.
    """
    raise NotImplementedError(
        "Override the `next_topic` fixture in the package's integration conftest."
    )


@pytest.fixture
def sync_publisher(
    next_topic: str, published_messages: list[QueueMessage]
) -> SyncQueuePublisher:
    """A publisher that records the hand-off instead of running the next worker."""
    broker = SyncQueueBroker()
    broker.register(next_topic, published_messages.append)
    return SyncQueuePublisher(broker)
