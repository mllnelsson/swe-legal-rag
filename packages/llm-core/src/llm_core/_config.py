from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm_core._protocol import LLMProvider


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    model: str = Field(default="gemini-2.0-flash", alias="LLM_MODEL")
    temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    max_tokens: int | None = Field(default=None, alias="LLM_MAX_TOKENS")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")


def create_provider(config: LLMConfig | None = None) -> LLMProvider:
    if config is None:
        config = LLMConfig()

    match config.provider:
        case "gemini":
            from llm_core.providers._gemini import GeminiProvider

            return GeminiProvider(config)
        case _:
            raise ValueError(f"Unknown LLM provider: {config.provider!r}")
