from shared.config import StorageBackendType, StorageSettings
from shared.errors import BackendConfigError
from shared.storage.base import StorageBackend


def create_storage_backend(settings: StorageSettings) -> StorageBackend:
    match settings.storage_backend:
        case StorageBackendType.LOCAL:
            from shared.storage.local import LocalStorageBackend

            return LocalStorageBackend(settings.local_storage_path)
        case StorageBackendType.GCS:
            from shared.storage.gcs import GCSStorageBackend

            # `StorageSettings`' model_validator rejects the gcs backend without a
            # bucket, so settings could not have been constructed at all.
            assert settings.gcs_bucket is not None
            return GCSStorageBackend(settings.gcs_bucket)
        case _:
            raise BackendConfigError(
                f"Unknown storage backend: {settings.storage_backend}"
            )
