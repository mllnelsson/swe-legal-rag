from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class MetadataSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    metadata_topic: str = "metadata"
    metadata_next_topic: str = "extract"


@lru_cache(maxsize=1)
def get_metadata_settings() -> MetadataSettings:
    return MetadataSettings()
