import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The embedding width, and the only copy of it `shared` can see.
#
# The real source of truth is `embedding.dimension` in llm_config.yaml, but
# `shared` must not import `ai` — `ai` depends on `shared`, not the other way
# round. So the value is restated here for the two consumers that live below
# that line: the `chunks.embedding` column width (`shared.models.chunk`) and the
# Alembic migration that created it. `ai.verify_embedding_dimension` exists to
# reconcile this with the YAML and with what the model actually emits, once, at
# startup — the dependency direction is why that check has to exist at all.
#
# Read at import time rather than through BaseSettings because a SQLAlchemy
# column type needs it while the module is being defined.
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
    # The storage root, not a PDF directory: keys carry their own prefix
    # (`documents/…`, `llm-traces/…`). `./data` because that is what .gitignore
    # covers — a default outside it writes crawled PDFs and whole prompts into
    # a directory git will offer to commit.
    local_storage_path: Path = Path("./data")
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
