"""Resolving which database the integration suite is allowed to touch.

Pure functions, no I/O. The integration suite truncates every table before each
test, so pointing it at the development database destroys locally crawled data.
`resolve_test_database_url` is the guard that makes that impossible rather than
merely discouraged.
"""

from __future__ import annotations

from sqlalchemy.engine import make_url

from shared.errors import SharedError

__all__ = [
    "IntegrationDatabaseError",
    "DEV_DATABASE_URL_DEFAULT",
    "TEST_DATABASE_SUFFIX",
    "database_name",
    "resolve_test_database_url",
    "to_async_url",
    "to_sync_url",
]

DEV_DATABASE_URL_DEFAULT = "postgresql://postgres:postgres@localhost:5432/overklagan"
TEST_DATABASE_SUFFIX = "_test"

SYNC_DRIVER = "postgresql+psycopg"
ASYNC_DRIVER = "postgresql+asyncpg"


class IntegrationDatabaseError(SharedError):
    """The integration suite was pointed at a database it must not touch."""


def database_name(url: str) -> str:
    """The database component of a connection URL."""
    return make_url(url).database or ""


def to_sync_url(url: str) -> str:
    """Rewrite a connection URL onto the synchronous psycopg driver."""
    return (
        make_url(url).set(drivername=SYNC_DRIVER).render_as_string(hide_password=False)
    )


def to_async_url(url: str) -> str:
    """Rewrite a connection URL onto the asyncpg driver."""
    return (
        make_url(url).set(drivername=ASYNC_DRIVER).render_as_string(hide_password=False)
    )


def resolve_test_database_url(dev_url: str, test_url: str | None) -> str:
    """Decide which database the integration suite runs against.

    `test_url` (from `TEST_DATABASE_URL`) wins when set. Otherwise the name is
    derived from `dev_url` by appending `_test`, so the common case needs no
    configuration at all — only `createdb overklagan_test`.

    Raises `IntegrationDatabaseError` when the result would be the development database.
    That is the whole point of this function: the suite truncates every table, so
    resolving to the dev database has to fail loudly rather than run.
    """
    dev_name = database_name(dev_url)
    if test_url is None:
        resolved = make_url(dev_url).set(database=f"{dev_name}{TEST_DATABASE_SUFFIX}")
        return resolved.render_as_string(hide_password=False)

    if database_name(test_url) == dev_name:
        raise IntegrationDatabaseError(
            f"Integration tests would run against the development database "
            f"{dev_name!r}, which they truncate before every test. "
            f"Unset TEST_DATABASE_URL to use the derived default "
            f"{dev_name}{TEST_DATABASE_SUFFIX}, or point it at a different database. "
            f"Create the default with: createdb -O postgres "
            f"{dev_name}{TEST_DATABASE_SUFFIX}"
        )
    return test_url
