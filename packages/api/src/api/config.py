from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrievalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    retrieval_top_k: int = 8
    retrieval_search_limit: int = 20
    retrieval_rerank_enabled: bool = False


@lru_cache(maxsize=1)
def get_retrieval_settings() -> RetrievalSettings:
    return RetrievalSettings()
