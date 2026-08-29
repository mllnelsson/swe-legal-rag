"""Embedding configuration, plus the LLM config surface re-exported from agent-kit.

The provider/role half of `llm_config.yaml` — declaring providers, assigning a
model to each task role, and the environment-wins precedence — now lives in
`agent_kit.config`, which is domain-free. This module keeps the *embedding* half,
which is this project's concern: the embedding backend set, the resolved
`EmbeddingConfig`, and the retrieval prefixes.

The two halves still share one file. `agent_kit`'s `LLMConfigDocument` carries
`embedding` as an opaque passthrough (it has no opinion on embeddings); this
module validates that block into an `EmbeddingSpec`, eagerly at load time so a
malformed embedding fails as loudly as it always did, and again when resolving.

The LLM-config names callers already import from `ai.llm_config`
(`LLMConfigDocument`, `resolve_role_config`, `get_llm_config`, …) are re-exported
here unchanged.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm_core import ProviderKind

from agent_kit.config import (
    CONFIG_FILENAME,
    CONFIG_PATH_ENV,
    SUPPORTED_VERSION,
    LLMConfigDocument,
    ProviderSpec,
    RoleDefaults,
    RoleSpec,
    api_key_for,
    find_config_path,
    get_llm_config,
    resolve_role_config,
    role_model_env_var,
    without_env_overrides,
)
from agent_kit.config import load_config_document as _load_config_document

from ai.errors import (
    LLMConfigInvalidError,
    UnsupportedEmbeddingBackendError,
)

__all__ = [
    # Re-exported LLM config surface (moved to agent_kit.config).
    "CONFIG_FILENAME",
    "CONFIG_PATH_ENV",
    "SUPPORTED_VERSION",
    "ProviderKind",
    "LLMConfigDocument",
    "ProviderSpec",
    "RoleDefaults",
    "RoleSpec",
    "find_config_path",
    "get_llm_config",
    "load_config_document",
    "resolve_role_config",
    "role_model_env_var",
    # Embedding config (this project's half).
    "EmbeddingBackend",
    "EmbeddingSpec",
    "EmbeddingConfig",
    "resolve_embedding_config",
    "get_embedding_prefixes",
]


class EmbeddingBackend(StrEnum):
    """What `create_embedding_provider` dispatches on.

    Deliberately a subset of `ProviderKind` plus `LOCAL`, and the shared members
    take their values *from* `ProviderKind` so the two cannot drift. Not every
    LLM host has an embeddings endpoint wired up here, so a kind absent from
    this enum is rejected by `resolve_embedding_config` — at config-resolution
    time, naming the offending YAML key, rather than at dispatch.

    LOCAL has no `ProviderKind` counterpart: it runs sentence-transformers
    in-process, so it has no host, no base URL and no key, and is written
    literally under `embedding.provider` instead of being declared as a provider.
    """

    LOCAL = "local"
    OPENAI_COMPATIBLE = ProviderKind.OPENAI_COMPATIBLE.value


class EmbeddingSpec(BaseModel):
    """The embedding model, its output width, and its retrieval prefixes."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    # Asymmetric models (e5) prefix the two sides of retrieval differently.
    # Empty strings are the correct setting for models that don't (bge-m3, jina).
    query_prefix: str = ""
    passage_prefix: str = ""


class EmbeddingConfig(BaseSettings):
    """Resolved embedding settings, in the shape the embedding providers read.

    Defined here rather than in `ai.embedding` so the resolver can build it
    without importing the module that consumes it.
    """

    model_config = SettingsConfigDict(populate_by_name=True)

    provider: EmbeddingBackend = Field(
        default=EmbeddingBackend.OPENAI_COMPATIBLE, alias="EMBEDDING_PROVIDER"
    )
    model: str = Field(default="", alias="EMBEDDING_MODEL")
    dimension: int = Field(default=1024, alias="EMBEDDING_DIMENSION")
    api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    # Escape hatch, environment-only and deliberately absent from `embedding:` in
    # llm_config.yaml: set it and no tokenizer is loaded at all. Declaring the
    # window in the file would be a second source of truth competing with the
    # model; declaring it in one environment is an operator saying "this box
    # cannot reach the tokenizer, here is the number, I take responsibility".
    window_override: int | None = Field(default=None, alias="EMBEDDING_WINDOW_OVERRIDE")


def load_config_document(path: Any = None) -> LLMConfigDocument:
    """Read and validate the config file, embedding block included.

    Wraps `agent_kit.config.load_config_document` — which validates the
    provider/role half — and then validates the embedding block into an
    `EmbeddingSpec`, so an embedding typo or an undeclared embedding provider
    fails here at load, exactly as it did before the split.
    """
    document = _load_config_document(path)
    _embedding_spec(document)
    return document


def _embedding_spec(document: LLMConfigDocument) -> EmbeddingSpec:
    """Validate and return the document's embedding block.

    Raises `LLMConfigInvalidError` for a missing, malformed, or undeclared-provider
    embedding block — the checks `LLMConfigDocument` used to do inline before
    `embedding` became an opaque passthrough on the agent-kit document.
    """
    raw = document.embedding
    if raw is None:
        raise LLMConfigInvalidError(
            f"{CONFIG_FILENAME} is missing the required 'embedding' block"
        )

    try:
        spec = EmbeddingSpec.model_validate(raw)
    except ValueError as exc:
        raise LLMConfigInvalidError(f"embedding block is invalid: {exc}") from exc

    known = sorted(document.providers)
    if spec.provider != EmbeddingBackend.LOCAL and spec.provider not in document.providers:
        raise LLMConfigInvalidError(
            f"embedding.provider {spec.provider!r} is neither "
            f"{EmbeddingBackend.LOCAL.value!r} nor declared under providers "
            f"(declared: {known})"
        )
    return spec


def resolve_embedding_config(
    document: LLMConfigDocument | None = None,
) -> EmbeddingConfig:
    """Build the embedding settings, applying the same environment-wins precedence."""
    document = document if document is not None else get_llm_config()
    spec = _embedding_spec(document)

    values: dict[str, Any] = {
        "provider": EmbeddingBackend.LOCAL,
        "model": spec.model,
        "dimension": spec.dimension,
    }

    # A hosted embedder is dispatched on its host's kind, not on the name the
    # file happens to give it, so a second OpenAI-compatible host needs no code.
    if spec.provider != EmbeddingBackend.LOCAL:
        provider = document.providers[spec.provider]
        values["provider"] = _embedding_backend_for(spec.provider, provider.kind)
        values["base_url"] = provider.base_url
        values["api_key"] = api_key_for(provider)

    return EmbeddingConfig(**without_env_overrides(EmbeddingConfig, values))


def _embedding_backend_for(name: str, kind: ProviderKind) -> EmbeddingBackend:
    """The embedding backend for a provider entry, or a refusal naming the key.

    Not every `ProviderKind` has an embeddings client here. Rejecting at
    resolution time points at the YAML key that is wrong; deferring to dispatch
    would report it as a mystery at the first embed call instead.
    """
    match kind:
        case ProviderKind.OPENAI_COMPATIBLE:
            return EmbeddingBackend.OPENAI_COMPATIBLE
        case ProviderKind.GEMINI | ProviderKind.NONE:
            raise UnsupportedEmbeddingBackendError(
                f"embedding.provider names {name!r}, whose kind is "
                f"{kind.value!r} — no embeddings client is wired up for it. Use "
                f"an {ProviderKind.OPENAI_COMPATIBLE.value!r} host or "
                f"{EmbeddingBackend.LOCAL.value!r}, which needs no key and runs "
                f"in-process."
            )


def get_embedding_prefixes(
    document: LLMConfigDocument | None = None,
) -> tuple[str, str]:
    """The (query, passage) prefixes for the configured embedding model.

    Both sides come from the same place so they cannot drift apart — prefixing
    only one side of an asymmetric model is worse than prefixing neither.
    """
    document = document if document is not None else get_llm_config()
    spec = _embedding_spec(document)
    return spec.query_prefix, spec.passage_prefix
