from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.enums import PipelineStep


class ChunkSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    chunk_topic: PipelineStep = PipelineStep.CHUNK
    chunk_next_topic: PipelineStep = PipelineStep.EMBED


@lru_cache(maxsize=1)
def get_chunk_settings() -> ChunkSettings:
    return ChunkSettings()
