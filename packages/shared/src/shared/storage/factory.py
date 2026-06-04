from shared.config import StorageBackendType, StorageSettings
from shared.storage.base import StorageBackend


def create_storage_backend(settings: StorageSettings) -> StorageBackend:
    match settings.storage_backend:
        case StorageBackendType.LOCAL:
            from shared.storage.local import LocalStorageBackend

            return LocalStorageBackend(settings.local_storage_path)
        case StorageBackendType.GCS:
            from shared.storage.gcs import GCSStorageBackend

            return GCSStorageBackend(settings.gcs_bucket)  # type: ignore[arg-type]
        case _:
            raise ValueError(f"Unknown storage backend: {settings.storage_backend}")
