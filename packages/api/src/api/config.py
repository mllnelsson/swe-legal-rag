from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatScript(StrEnum):
    """Which canned event sequence `POST /api/chat` replays, if any.

    A development switch for looking at agent mode without paying for a model
    run — see `api.dev.chat_scripts`. `OFF` is the default and the only value
    that runs the real agent.
    """

    OFF = "off"
    # Pick per turn from the message: a short one is a conversational turn, a
    # longer one a research question. Lets both shapes be seen without a
    # restart.
    AUTO = "auto"
    RESEARCH = "research"
    DIRECT = "direct"
    ERROR = "error"


class DevSettings(BaseSettings):
    """Switches that exist for developing against this API, not for serving it.

    Typed as an enum rather than a string so a misspelt `CHAT_SCRIPT` fails at
    startup, instead of falling through to the real agent and a surprise bill.
    """

    model_config = SettingsConfigDict(env_prefix="")

    chat_script: ChatScript = ChatScript.OFF


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    api_cors_origins: list[str] = ["http://localhost:5173"]


class SessionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    session_max_history_turns: int = 10


class SearchSettings(BaseSettings):
    """Bounds for the deterministic search API.

    Also the bounds the conversational agent searches under: its
    `search_decisions` tool is a wrapper over this same path, so the two cannot
    drift apart. Agent-loop bounds — iterations, reading budget, citation cap —
    live in `agents.ChatAgentSettings` instead, next to the agent they govern.
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
    # Cosine similarity a chunk must reach before the vector arm will return it.
    #
    # Without a floor the arm returns `search_arm_limit` neighbours for every
    # query, however unrelated — nearest is not the same as near — so an empty
    # result is unreachable and every caller sees a full, confident-looking page.
    # The fused RRF score cannot expose that, since it is derived from rank.
    #
    # The value is model- and corpus-specific rather than a property of the
    # algorithm, so it is declared in `.env` where it can be tuned per
    # environment; the default here is what `.env` ships with. The calibration
    # behind it lives in /retrieval/deterministic-search.md#the-similarity-floor.
    search_min_vector_similarity: float = 0.78


@lru_cache(maxsize=1)
def get_dev_settings() -> DevSettings:
    return DevSettings()


@lru_cache(maxsize=1)
def get_session_settings() -> SessionSettings:
    return SessionSettings()


@lru_cache(maxsize=1)
def get_search_settings() -> SearchSettings:
    return SearchSettings()
