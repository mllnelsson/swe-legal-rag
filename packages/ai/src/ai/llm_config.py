"""Declarative LLM and embedding configuration, loaded from `llm_config.yaml`.

Which model and which provider each task uses is a deployment decision that
changes far more often than the code around it, so it lives in one checked-in
file rather than being spread across a dozen environment variables. Adding a
task with its own model is a YAML edit; no Python change is required.

The file declares providers once and lets roles reference them by name, so a
base URL and an API key variable are stated in exactly one place and shared by
the LLM roles and the embedder.

**Precedence** (highest first): environment variable, then the role's own entry,
then `defaults`, then the field default on `llm_core.LLMConfig`. The file is the
checked-in default; the environment is the deployment override. Note this is the
opposite of pydantic-settings' native ordering — see `_without_env_overrides`.

API keys are never read from this file. A provider names the environment
variable holding its key; the value stays in `.env` or Secret Manager.

The loader lives in `ai` rather than `llm-core` because `llm-core` is
project-agnostic and knows nothing about a file at this project's root.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm_core import LLMConfig, ProviderKind

from ai.errors import (
    LLMConfigInvalidError,
    LLMConfigNotFoundError,
    UnknownLLMRoleError,
    UnsupportedEmbeddingBackendError,
)

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "llm_config.yaml"
CONFIG_PATH_ENV = "LLM_CONFIG_PATH"
SUPPORTED_VERSION = 1

# Per-role model override, e.g. LLM_MODEL_CHAT. Predates this file as
# LLM_MODEL_STRUCTURED/SUMMARIZE/CHAT and keeps working unchanged; a role added
# to the YAML gets its own override name for free.
_ROLE_MODEL_ENV_TEMPLATE = "LLM_MODEL_{role}"


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


class ProviderSpec(BaseModel):
    """One LLM host: how to talk to it and where its key comes from."""

    model_config = ConfigDict(extra="forbid")

    kind: ProviderKind
    base_url: str | None = None
    api_key_env: str


class RoleDefaults(BaseModel):
    """Values inherited by every role that omits them."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    temperature: float = 0.0
    max_tokens: int | None = None
    stream_usage: bool = True


class RoleSpec(BaseModel):
    """One task's model, plus any per-task override of the defaults."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    provider: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stream_usage: bool | None = None


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


class LLMConfigDocument(BaseModel):
    """The whole of `llm_config.yaml`, validated.

    `extra="forbid"` throughout: a mistyped key that silently does nothing is
    worse than a startup failure, because it looks like the setting took effect.
    """

    model_config = ConfigDict(extra="forbid")

    version: int
    providers: dict[str, ProviderSpec]
    defaults: RoleDefaults
    roles: dict[str, RoleSpec]
    embedding: EmbeddingSpec

    @model_validator(mode="after")
    def _check_references(self) -> LLMConfigDocument:
        if self.version != SUPPORTED_VERSION:
            raise ValueError(
                f"Unsupported llm_config version {self.version}; "
                f"this build understands version {SUPPORTED_VERSION}"
            )

        known = sorted(self.providers)
        if self.defaults.provider not in self.providers:
            raise ValueError(
                f"defaults.provider {self.defaults.provider!r} is not declared "
                f"under providers (declared: {known})"
            )

        for role, spec in self.roles.items():
            if spec.provider is not None and spec.provider not in self.providers:
                raise ValueError(
                    f"roles.{role}.provider {spec.provider!r} is not declared "
                    f"under providers (declared: {known})"
                )

        if (
            self.embedding.provider != EmbeddingBackend.LOCAL
            and self.embedding.provider not in self.providers
        ):
            raise ValueError(
                f"embedding.provider {self.embedding.provider!r} is neither "
                f"{EmbeddingBackend.LOCAL.value!r} nor declared under providers "
                f"(declared: {known})"
            )

        return self


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


def find_config_path() -> Path:
    """Locate `llm_config.yaml`.

    `LLM_CONFIG_PATH` wins if set. Otherwise walk up from the working directory:
    this is a uv workspace and pytest is routinely run from a package subdirectory,
    where the repo root is not the cwd.
    """
    override = os.environ.get(CONFIG_PATH_ENV)
    if override:
        path = Path(override)
        if not path.is_file():
            raise LLMConfigNotFoundError(
                f"{CONFIG_PATH_ENV} points at {path}, which does not exist"
            )
        return path

    start = Path.cwd().resolve()
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate

    raise LLMConfigNotFoundError(
        f"No {CONFIG_FILENAME} found in {start} or any parent directory. "
        f"Set {CONFIG_PATH_ENV} to point at it explicitly."
    )


def load_config_document(path: Path | None = None) -> LLMConfigDocument:
    """Read and validate the config file. Prefer `get_llm_config()` in callers."""
    path = path or find_config_path()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise LLMConfigInvalidError(f"Could not read {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise LLMConfigInvalidError(
            f"{path} must contain a YAML mapping at the top level, got {type(raw).__name__}"
        )

    try:
        return LLMConfigDocument.model_validate(raw)
    except ValueError as exc:
        raise LLMConfigInvalidError(f"{path} is invalid: {exc}") from exc


@lru_cache(maxsize=1)
def get_llm_config() -> LLMConfigDocument:
    """The process-wide config document, read once."""
    return load_config_document()


def resolve_role_config(
    role: str, document: LLMConfigDocument | None = None
) -> LLMConfig:
    """Build the `llm_core.LLMConfig` for a named role, applying precedence."""
    document = document if document is not None else get_llm_config()

    spec = document.roles.get(role)
    if spec is None:
        raise UnknownLLMRoleError(
            f"No LLM role named {role!r} in {CONFIG_FILENAME}; "
            f"declared roles: {sorted(document.roles)}"
        )

    defaults = document.defaults
    provider = document.providers[spec.provider or defaults.provider]

    _warn_if_env_masks_role_provider(role, spec, provider.kind)

    inherited = {
        "provider": provider.kind,
        "base_url": provider.base_url,
        "api_key": os.environ.get(provider.api_key_env),
        "temperature": _first_set(spec.temperature, defaults.temperature),
        "max_tokens": _first_set(spec.max_tokens, defaults.max_tokens),
        "stream_usage": _first_set(spec.stream_usage, defaults.stream_usage),
    }

    # `model` is passed unconditionally rather than through the helper: its own
    # env alias is the pre-roles global LLM_MODEL, and letting that through would
    # collapse every role onto one model. The per-role name is the override.
    return LLMConfig(
        model=os.environ.get(role_model_env_var(role), spec.model),
        **_without_env_overrides(LLMConfig, inherited),
    )


def resolve_embedding_config(
    document: LLMConfigDocument | None = None,
) -> EmbeddingConfig:
    """Build the embedding settings, applying the same precedence."""
    document = document if document is not None else get_llm_config()
    spec = document.embedding

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
        values["api_key"] = os.environ.get(provider.api_key_env)

    return EmbeddingConfig(**_without_env_overrides(EmbeddingConfig, values))


def _embedding_backend_for(name: str, kind: ProviderKind) -> EmbeddingBackend:
    """The embedding backend for a provider entry, or a refusal naming the key.

    Not every `ProviderKind` has an embeddings client here. Rejecting at
    resolution time points at the YAML key that is wrong; deferring to dispatch
    would report it as a mystery at the first embed call instead.
    """
    match kind:
        case ProviderKind.OPENAI_COMPATIBLE:
            return EmbeddingBackend.OPENAI_COMPATIBLE
        case ProviderKind.GEMINI:
            raise UnsupportedEmbeddingBackendError(
                f"embedding.provider names {name!r}, whose kind is "
                f"{kind.value!r} — no embeddings client is wired up for it. Use "
                f"an {ProviderKind.OPENAI_COMPATIBLE.value!r} host or "
                f"{EmbeddingBackend.LOCAL.value!r}."
            )


def get_embedding_prefixes(
    document: LLMConfigDocument | None = None,
) -> tuple[str, str]:
    """The (query, passage) prefixes for the configured embedding model.

    Both sides come from the same place so they cannot drift apart — prefixing
    only one side of an asymmetric model is worse than prefixing neither.
    """
    document = document if document is not None else get_llm_config()
    return document.embedding.query_prefix, document.embedding.passage_prefix


def role_model_env_var(role: str) -> str:
    """The environment variable that overrides a role's model."""
    return _ROLE_MODEL_ENV_TEMPLATE.format(role=role.upper().replace("-", "_"))


def _first_set[T](override: T | None, fallback: T) -> T:
    return fallback if override is None else override


def _warn_if_env_masks_role_provider(
    role: str, spec: RoleSpec, kind: ProviderKind
) -> None:
    """Say so when LLM_PROVIDER overrides a provider the role asked for by name.

    LLM_PROVIDER is process-wide and pre-dates per-role providers, so a stale one
    in `.env` silently flattens every role onto one host — and the YAML still
    reads as though the per-role choice is in effect. Env winning is intended;
    doing it invisibly is not.
    """
    env_provider = os.environ.get(_env_alias(LLMConfig, "provider"))
    if spec.provider is None or env_provider is None or env_provider == kind:
        return

    logger.warning(
        "Role %r declares provider %r (kind %s) in %s, but %s=%s is set in the "
        "environment and takes precedence. Unset it to let the file decide.",
        role,
        spec.provider,
        kind.value,
        CONFIG_FILENAME,
        _env_alias(LLMConfig, "provider"),
        env_provider,
    )


def _without_env_overrides(
    settings_type: type[BaseSettings], values: dict[str, Any]
) -> dict[str, Any]:
    """Drop entries whose environment variable is set.

    pydantic-settings ranks init keyword arguments *above* environment variables.
    This project wants the reverse, so the way to let the environment win is to
    withhold the keyword argument and leave the field for pydantic to fill.
    """
    return {
        name: value
        for name, value in values.items()
        if _env_alias(settings_type, name) not in os.environ
    }


def _env_alias(settings_type: type[BaseSettings], field_name: str) -> str:
    """The environment variable a settings field reads, taken from the model itself.

    Read off the field rather than restated here, so the two can't disagree.
    """
    alias = settings_type.model_fields[field_name].alias
    return alias if alias is not None else field_name.upper()
