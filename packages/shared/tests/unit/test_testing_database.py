"""The guard that keeps the integration suite off the development database.

This is the one piece of test infrastructure that must not fail open: the suite
truncates every table before each test, so a resolution bug costs whoever ran it
their local corpus.
"""

import pytest

from shared.testing.database import (
    IntegrationDatabaseError,
    database_name,
    resolve_test_database_url,
    to_async_url,
    to_sync_url,
)

DEV_URL = "postgresql://postgres:postgres@localhost:5432/overklagan"


def test_derived_default_appends_the_test_suffix():
    resolved = resolve_test_database_url(DEV_URL, None)

    assert database_name(resolved) == "overklagan_test"


def test_derived_default_keeps_host_port_and_credentials():
    resolved = resolve_test_database_url(DEV_URL, None)

    assert resolved == "postgresql://postgres:postgres@localhost:5432/overklagan_test"


def test_explicit_test_url_is_used_verbatim():
    explicit = "postgresql://ci:secret@db.internal:6543/scratch"

    assert resolve_test_database_url(DEV_URL, explicit) == explicit


def test_test_url_naming_the_dev_database_is_refused():
    with pytest.raises(IntegrationDatabaseError, match="overklagan"):
        resolve_test_database_url(DEV_URL, DEV_URL)


def test_refusal_is_by_database_name_not_url_spelling():
    """A different host or driver spelling of the same name is still a refusal."""
    same_database_other_driver = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/overklagan"
    )

    with pytest.raises(IntegrationDatabaseError):
        resolve_test_database_url(DEV_URL, same_database_other_driver)


def test_refusal_message_names_the_fix():
    with pytest.raises(
        IntegrationDatabaseError, match="createdb -O postgres overklagan_test"
    ):
        resolve_test_database_url(DEV_URL, DEV_URL)


def test_driver_rewrites_preserve_the_database():
    assert to_sync_url(DEV_URL).startswith("postgresql+psycopg://")
    assert to_async_url(DEV_URL).startswith("postgresql+asyncpg://")
    assert database_name(to_sync_url(DEV_URL)) == "overklagan"
    assert database_name(to_async_url(DEV_URL)) == "overklagan"


def test_driver_rewrites_keep_the_password():
    """The URL is handed to a real engine; a redacted password would not connect."""
    assert "postgres:postgres@" in to_async_url(DEV_URL)
