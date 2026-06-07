from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ParseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    parse_topic: str = "parse"
    parse_next_topic: str = "metadata"


@lru_cache(maxsize=1)
def get_parse_settings() -> ParseSettings:
    return ParseSettings()
