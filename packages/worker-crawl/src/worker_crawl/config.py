from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.enums import PipelineStep
from worker_crawl.odata import ODataConfig
from worker_crawl.years import CURRENT_SPEC

DEFAULT_API_BASE = "https://www.svenskakyrkan.se/webapi/api-v3/odata/"
DEFAULT_DOCUMENT_URL_TEMPLATE = (
    "https://www.svenskakyrkan.se/default.aspx?id={document_id}&ptid="
)
# The Svenska kyrkan web whose decision documents we crawl.
DEFAULT_WEB_ID = 1374643


class CrawlSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    # Required, deliberately without a default: the working key was captured from browser
    # devtools and its provenance is unverified, so it is supplied per-environment via
    # CRAWL_API_KEY rather than committed. Startup fails loudly if it is unset.
    crawl_api_key: str

    crawl_api_base: str = DEFAULT_API_BASE
    crawl_document_url_template: str = DEFAULT_DOCUMENT_URL_TEMPLATE
    crawl_web_id: int = DEFAULT_WEB_ID
    crawl_years: str = CURRENT_SPEC
    crawl_page_size: int = 100
    crawl_rate_limit_delay: float = 0.5
    crawl_max_retries: int = 3
    crawl_request_timeout: int = 30
    crawl_topic: PipelineStep = PipelineStep.DOWNLOAD


def to_odata_config(settings: CrawlSettings) -> ODataConfig:
    return ODataConfig(
        base_url=settings.crawl_api_base,
        api_key=settings.crawl_api_key,
        web_id=settings.crawl_web_id,
        document_url_template=settings.crawl_document_url_template,
        page_size=settings.crawl_page_size,
        request_timeout=settings.crawl_request_timeout,
        rate_limit_delay=settings.crawl_rate_limit_delay,
        max_retries=settings.crawl_max_retries,
    )


@lru_cache(maxsize=1)
def get_crawl_settings() -> CrawlSettings:
    return CrawlSettings()
