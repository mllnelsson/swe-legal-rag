from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.enums import PipelineStep


class CrawlSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    crawl_source_url: str
    crawl_request_timeout: int = 30
    crawl_topic: PipelineStep = PipelineStep.DOWNLOAD


@lru_cache(maxsize=1)
def get_crawl_settings() -> CrawlSettings:
    return CrawlSettings()
