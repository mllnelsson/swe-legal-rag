from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class CrawlSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    crawl_source_url: str
    crawl_request_timeout: int = 30
    crawl_topic: str = "download"


@lru_cache(maxsize=1)
def get_crawl_settings() -> CrawlSettings:
    return CrawlSettings()
