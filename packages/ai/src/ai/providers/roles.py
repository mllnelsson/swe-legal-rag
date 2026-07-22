"""Per-task LLM model assignment.

`llm_core.LLMConfig` carries a single `model` field — one process-wide model
for every call. This project needs three different models for three
different cost/quality profiles instead of one model for everything:

- structured: high-volume, JSON-schema output (query decomposition, metadata
  and entity extraction, reranking) — a cheap, JSON-schema-capable model.
- summarize: one call per ingested document, no structured output, may see
  long documents — a larger-context model.
- chat: low-volume, streaming, user-facing answer synthesis — a stronger
  model, since it's not run at ingestion scale.

Each `create_*_llm_provider()` below builds an `LLMConfig` that only
overrides `model`; `provider`/API key/`base_url`/temperature still resolve
from the environment exactly as `llm_core.create_provider()` would use them
normally.

The defaults here are Berget model IDs. Switching `LLM_PROVIDER` back to
"gemini" also requires overriding `LLM_MODEL_STRUCTURED`, `LLM_MODEL_SUMMARIZE`,
and `LLM_MODEL_CHAT` to valid Gemini model names — these defaults will not
resolve against Gemini's API.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm_core import LLMConfig, LLMProvider, create_provider


class LLMRoleConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    model_structured: str = Field(
        default="mistralai/Mistral-Small-3.2-24B-Instruct-2506",
        alias="LLM_MODEL_STRUCTURED",
    )
    model_summarize: str = Field(
        default="mistralai/Mistral-Medium-3.5-128B",
        alias="LLM_MODEL_SUMMARIZE",
    )
    model_chat: str = Field(
        default="zai-org/GLM-5.2",
        alias="LLM_MODEL_CHAT",
    )


def create_structured_llm_provider() -> LLMProvider:
    return create_provider(LLMConfig(model=LLMRoleConfig().model_structured))


def create_summarize_llm_provider() -> LLMProvider:
    return create_provider(LLMConfig(model=LLMRoleConfig().model_summarize))


def create_chat_llm_provider() -> LLMProvider:
    return create_provider(LLMConfig(model=LLMRoleConfig().model_chat))
