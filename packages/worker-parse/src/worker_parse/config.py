from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.enums import PipelineStep


class ParseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    parse_topic: PipelineStep = PipelineStep.PARSE
    parse_next_topic: PipelineStep = PipelineStep.METADATA


@lru_cache(maxsize=1)
def get_parse_settings() -> ParseSettings:
    return ParseSettings()
