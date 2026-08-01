from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.enums import PipelineStep


class ExtractSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    extract_topic: PipelineStep = PipelineStep.EXTRACT
    extract_next_topic: PipelineStep = PipelineStep.CHUNK


@lru_cache(maxsize=1)
def get_extract_settings() -> ExtractSettings:
    return ExtractSettings()
