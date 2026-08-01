"""What is worth testing in `shared.config` is the fail-fast rules we wrote.

Reading env vars, applying field defaults and caching are pydantic-settings and
`functools`; a test over those only breaks when a dependency changes its API. The
two `@model_validator(mode="after")` bodies are ours, and each encodes a real
decision: a backend that needs a destination must not start without one.
"""

import pytest
from pydantic import ValidationError

from shared.config import QueueSettings, StorageSettings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_gcs_storage_without_a_bucket_is_rejected(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "gcs")
    monkeypatch.delenv("GCS_BUCKET", raising=False)

    with pytest.raises(ValidationError):
        StorageSettings()


def test_pubsub_queue_without_a_project_is_rejected(monkeypatch):
    monkeypatch.setenv("QUEUE_BACKEND", "pubsub")
    monkeypatch.delenv("PUBSUB_PROJECT_ID", raising=False)

    with pytest.raises(ValidationError):
        QueueSettings()
