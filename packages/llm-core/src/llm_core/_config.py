from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm_core._protocol import LLMProvider


class ProviderKind(StrEnum):
    """The client implementation a provider maps onto.

    A *kind* is a wire protocol, not a vendor: every host speaking the OpenAI
    chat-completions API is one `OPENAI_COMPATIBLE` entry apart, distinguished
    by `base_url` alone. Adding such a host needs no code.
    """

    OPENAI_COMPATIBLE = "openai_compatible"
    GEMINI = "gemini"


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    provider: ProviderKind = Field(
        default=ProviderKind.OPENAI_COMPATIBLE, alias="LLM_PROVIDER"
    )
    model: str = Field(default="gemini-2.0-flash", alias="LLM_MODEL")
    temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    max_tokens: int | None = Field(default=None, alias="LLM_MAX_TOKENS")
    # One host-agnostic key. Which environment variable it came from is the
    # caller's business: `ai.llm_config` reads the name off the provider entry's
    # `api_key_env`, so a per-host variable never has to be named here.
    api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    # Asking for token usage on a stream is an extra request parameter, and a
    # host that rejects it fails the whole call. Streaming is the user-facing
    # chat path, so this stays switchable without a code change.
    stream_usage: bool = Field(default=True, alias="LLM_STREAM_USAGE")


def create_provider(config: LLMConfig | None = None) -> LLMProvider:
    """Build the client for `config.provider`.

    No fallback case: `provider` is a `ProviderKind`, so pydantic rejects an
    unknown value when the config is built — at the point the bad setting was
    supplied, rather than later at dispatch. Adding a kind without a case here
    is a type error, which is the whole reason this dispatches on an enum.
    """
    if config is None:
        config = LLMConfig()

    match config.provider:
        case ProviderKind.GEMINI:
            from llm_core.providers._gemini import GeminiProvider

            return GeminiProvider(config)
        case ProviderKind.OPENAI_COMPATIBLE:
            from llm_core.providers._openai_compatible import OpenAiCompatibleProvider

            return OpenAiCompatibleProvider(config)
