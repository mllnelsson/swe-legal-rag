from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.enums import PipelineStep


class EmbedSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    embed_topic: PipelineStep = PipelineStep.EMBED


@lru_cache(maxsize=1)
def get_embed_settings() -> EmbedSettings:
    return EmbedSettings()
