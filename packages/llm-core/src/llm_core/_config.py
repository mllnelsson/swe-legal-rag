from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm_core._protocol import LLMProvider

# Fallback for the OpenAI-compatible client when no base URL is configured.
# Berget was the first host wired up; `base_url` overrides it for any other.
BERGET_BASE_URL = "https://api.berget.ai/v1"


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    provider: str = Field(default="berget", alias="LLM_PROVIDER")
    model: str = Field(default="gemini-2.0-flash", alias="LLM_MODEL")
    temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    max_tokens: int | None = Field(default=None, alias="LLM_MAX_TOKENS")
    # Host-agnostic key, used when the caller resolved it itself — a config file
    # naming the variable per host, say. The two named fields below stay as the
    # direct-from-environment path and are what a provider falls back to.
    api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    berget_api_key: str | None = Field(default=None, alias="BERGET_API_KEY")
    base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    # Asking for token usage on a stream is an extra request parameter, and a
    # host that rejects it fails the whole call. Streaming is the user-facing
    # chat path, so this stays switchable without a code change.
    stream_usage: bool = Field(default=True, alias="LLM_STREAM_USAGE")


def create_provider(config: LLMConfig | None = None) -> LLMProvider:
    if config is None:
        config = LLMConfig()

    match config.provider:
        case "gemini":
            from llm_core.providers._gemini import GeminiProvider

            return GeminiProvider(config)
        # "openai_compatible" names the client; "berget" is the original value
        # from before hosts were configured by kind, kept so existing
        # LLM_PROVIDER=berget environments keep resolving.
        case "openai_compatible" | "berget":
            from llm_core.providers._openai_compatible import OpenAiCompatibleProvider

            return OpenAiCompatibleProvider(config, default_base_url=BERGET_BASE_URL)
        case _:
            raise ValueError(f"Unknown LLM provider: {config.provider!r}")
