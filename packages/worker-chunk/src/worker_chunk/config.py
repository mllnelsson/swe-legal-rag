from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ChunkSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    chunk_topic: str = "chunk"
    chunk_next_topic: str = "embed"


@lru_cache(maxsize=1)
def get_chunk_settings() -> ChunkSettings:
    return ChunkSettings()
