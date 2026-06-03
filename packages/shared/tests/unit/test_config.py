import pytest
from pydantic import ValidationError

from shared.config import (
    DatabaseSettings,
    QueueBackendType,
    QueueSettings,
    Settings,
    StorageBackendType,
    StorageSettings,
    get_settings,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_storage_backend_type_local_value():
    assert StorageBackendType.LOCAL == "local"


def test_storage_backend_type_gcs_value():
    assert StorageBackendType.GCS == "gcs"


def test_queue_backend_type_sync_value():
    assert QueueBackendType.SYNC == "sync"


def test_queue_backend_type_pubsub_value():
    assert QueueBackendType.PUBSUB == "pubsub"


def test_database_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        DatabaseSettings()


def test_database_settings_reads_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    settings = DatabaseSettings()
    assert settings.database_url == "postgresql://user:pass@localhost/db"


def test_storage_settings_defaults(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    settings = StorageSettings()
    assert settings.storage_backend == StorageBackendType.LOCAL
    assert settings.gcs_bucket is None


def test_storage_settings_gcs_requires_bucket(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "gcs")
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    with pytest.raises(ValidationError):
        StorageSettings()


def test_storage_settings_gcs_with_bucket(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "gcs")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    settings = StorageSettings()
    assert settings.storage_backend == StorageBackendType.GCS
    assert settings.gcs_bucket == "my-bucket"


def test_queue_settings_defaults(monkeypatch):
    monkeypatch.delenv("QUEUE_BACKEND", raising=False)
    settings = QueueSettings()
    assert settings.queue_backend == QueueBackendType.SYNC
    assert settings.pubsub_project_id is None


def test_queue_settings_pubsub_requires_project_id(monkeypatch):
    monkeypatch.setenv("QUEUE_BACKEND", "pubsub")
    monkeypatch.delenv("PUBSUB_PROJECT_ID", raising=False)
    with pytest.raises(ValidationError):
        QueueSettings()


def test_queue_settings_pubsub_with_project_id(monkeypatch):
    monkeypatch.setenv("QUEUE_BACKEND", "pubsub")
    monkeypatch.setenv("PUBSUB_PROJECT_ID", "my-project")
    settings = QueueSettings()
    assert settings.queue_backend == QueueBackendType.PUBSUB
    assert settings.pubsub_project_id == "my-project"


def test_settings_storage_and_queue_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("QUEUE_BACKEND", raising=False)
    settings = Settings()
    assert settings.storage.storage_backend == StorageBackendType.LOCAL
    assert settings.queue.queue_backend == QueueBackendType.SYNC


def test_get_settings_returns_same_instance(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
