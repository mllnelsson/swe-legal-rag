from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    api_cors_origins: list[str] = ["http://localhost:5173"]


class RetrievalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    retrieval_top_k: int = 8
    retrieval_search_limit: int = 20
    retrieval_rerank_enabled: bool = False
    # Appendices hold the appealed decision, so they are out of the primary search
    # by default. Set true to search the whole corpus regardless of what the query
    # planner decides; retrieval also widens on its own when body-only finds nothing.
    retrieval_include_appendices: bool = False


class SessionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    session_max_history_turns: int = 10


class SearchSettings(BaseSettings):
    """Bounds for the deterministic search API.

    Separate from ``RetrievalSettings``, which tunes the chat retrieval path: the
    two answer different questions and should be tunable without disturbing each
    other.
    """

    model_config = SettingsConfigDict(env_prefix="")

    search_default_limit: int = 10
    search_max_limit: int = 50
    # Per-arm, per-query cap. Total chunks entering fusion is bounded by
    # this * (1 vector arm + N text arms).
    search_arm_limit: int = 50
    search_chunks_per_document: int = 3
    # Ceiling on how many documents a metadata filter may narrow to before it is
    # handed to the search arms as an `IN` list.
    search_candidate_limit: int = 500
    search_max_query_variants: int = 3
    # Expansion helps the lexical arm, where a paraphrase changes which stems
    # match. The vector arm already matches semantically, and a longer paraphrase
    # tends to blur the embedding rather than sharpen it.
    search_expand_vector_arm: bool = False


@lru_cache(maxsize=1)
def get_retrieval_settings() -> RetrievalSettings:
    return RetrievalSettings()


@lru_cache(maxsize=1)
def get_session_settings() -> SessionSettings:
    return SessionSettings()


@lru_cache(maxsize=1)
def get_search_settings() -> SearchSettings:
    return SearchSettings()
