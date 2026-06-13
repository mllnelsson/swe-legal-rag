from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbedSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    embed_topic: str = "embed"


@lru_cache(maxsize=1)
def get_embed_settings() -> EmbedSettings:
    return EmbedSettings()
