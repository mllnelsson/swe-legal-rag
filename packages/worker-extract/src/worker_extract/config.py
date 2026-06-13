from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ExtractSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    extract_topic: str = "extract"
    extract_next_topic: str = "chunk"


@lru_cache(maxsize=1)
def get_extract_settings() -> ExtractSettings:
    return ExtractSettings()
