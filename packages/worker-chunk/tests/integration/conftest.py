"""Database and queue fixtures come from the `shared.testing.fixtures` plugin.
Only the hand-off topic is specific to this worker.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def next_topic() -> str:
    return "embed"
