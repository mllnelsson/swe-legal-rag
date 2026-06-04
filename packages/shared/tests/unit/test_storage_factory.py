import pytest

from shared.config import StorageBackendType, StorageSettings
from shared.storage.factory import create_storage_backend
from shared.storage.local import LocalStorageBackend


def test_factory_returns_local_backend(tmp_path):
    settings = StorageSettings(storage_backend=StorageBackendType.LOCAL, local_storage_path=tmp_path)
    backend = create_storage_backend(settings)
    assert isinstance(backend, LocalStorageBackend)


def test_factory_raises_for_unknown_backend(tmp_path):
    settings = StorageSettings(storage_backend=StorageBackendType.LOCAL, local_storage_path=tmp_path)
    settings_copy = settings.model_copy(update={"storage_backend": "unknown"})
    with pytest.raises(ValueError):
        create_storage_backend(settings_copy)  # type: ignore[arg-type]
