"""Repository-root pytest configuration.

Two things live here because pytest only honours them at the root: the global
fixture plugin, and the rule that decides what counts as an integration test.

Directory location is that rule. Anything under a `tests/integration/` directory
is an integration test whether or not its author remembered to say so — a marker
applied by hand is a marker that eventually gets forgotten, and a forgotten one
puts a database-truncating test into the default run.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["shared.testing.fixtures"]

INTEGRATION_MARKER = "integration"
INTEGRATION_TEST_DIRECTORY = "tests/integration/"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if INTEGRATION_TEST_DIRECTORY in item.path.as_posix():
            item.add_marker(INTEGRATION_MARKER)

    # Checked once here rather than in the fixture so a misconfigured
    # TEST_DATABASE_URL ends the run with one message, before any test has had
    # the chance to truncate anything.
    if any(item.get_closest_marker(INTEGRATION_MARKER) for item in items):
        # Imported here, not at module scope: importing a plugin module before
        # pytest registers it costs that module its assertion rewriting.
        from shared.testing.fixtures import (
            check_test_database_is_not_the_development_one,
        )

        check_test_database_is_not_the_development_one()
