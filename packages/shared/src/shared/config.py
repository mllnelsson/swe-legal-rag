import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Matches `ai.embedding.DEFAULT_EMBEDDING_MODEL` (intfloat/multilingual-e5-large).
# Changing this requires a migration recreating `chunks.embedding` at the new width.
DEFAULT_EMBEDDING_DIMENSION = 1024

EMBEDDING_DIMENSION: int = int(
    os.environ.get("EMBEDDING_DIMENSION", DEFAULT_EMBEDDING_DIMENSION)
)


class StorageBackendType(StrEnum):
    LOCAL = "local"
    GCS = "gcs"


class QueueBackendType(StrEnum):
    SYNC = "sync"
    PUBSUB = "pubsub"


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    database_url: str


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    storage_backend: StorageBackendType = StorageBackendType.LOCAL
    local_storage_path: Path = Path("./storage")
    gcs_bucket: str | None = None

    @model_validator(mode="after")
    def _validate_gcs(self) -> "StorageSettings":
        if self.storage_backend == StorageBackendType.GCS and not self.gcs_bucket:
            raise ValueError("gcs_bucket is required when storage_backend is gcs")
        return self


class QueueSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    queue_backend: QueueBackendType = QueueBackendType.SYNC
    pubsub_project_id: str | None = None

    @model_validator(mode="after")
    def _validate_pubsub(self) -> "QueueSettings":
        if self.queue_backend == QueueBackendType.PUBSUB and not self.pubsub_project_id:
            raise ValueError(
                "pubsub_project_id is required when queue_backend is pubsub"
            )
        return self


class Settings(BaseModel):
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    queue: QueueSettings = Field(default_factory=QueueSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
