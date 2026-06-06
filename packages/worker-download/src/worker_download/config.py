from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DownloadSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    download_request_timeout: int = 60
    download_topic: str = "download"
    download_next_topic: str = "parse"
    download_max_retries: int = 3
    download_rate_limit_delay: float = 0.5


@lru_cache(maxsize=1)
def get_download_settings() -> DownloadSettings:
    return DownloadSettings()
