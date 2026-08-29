"""The LLM config document: providers, per-task roles, and their defaults.

Which model and which provider each task uses is a deployment decision that
changes far more often than the code around it, so it lives in one checked-in
file rather than being spread across a dozen environment variables. Swapping a
task's model is a YAML edit.

The file declares providers once and lets roles reference them by name, so a
base URL and an API key variable are stated in exactly one place.

`embedding` is carried as an opaque passthrough: the agent core has no opinion
on embeddings, but the document has to *tolerate* the key so a host that does
(and validates it itself) can keep everything in one file without this layer's
`extra="forbid"` rejecting it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from llm_core import ProviderKind

CONFIG_FILENAME = "llm_config.yaml"
CONFIG_PATH_ENV = "LLM_CONFIG_PATH"
SUPPORTED_VERSION = 1


class ProviderSpec(BaseModel):
    """One LLM host: how to talk to it and where its key comes from."""

    model_config = ConfigDict(extra="forbid")

    kind: ProviderKind
    base_url: str | None = None
    # Optional in the schema but required by the validator below for every kind
    # that talks to a host. `none` has nowhere to send a key.
    api_key_env: str | None = None

    @model_validator(mode="after")
    def _check_api_key_env(self) -> ProviderSpec:
        if self.kind is not ProviderKind.NONE and self.api_key_env is None:
            raise ValueError(
                f"a provider of kind {self.kind.value!r} must name its "
                f"api_key_env; only {ProviderKind.NONE.value!r} may omit it"
            )
        return self


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


class LLMConfigDocument(BaseModel):
    """The whole config document, validated.

    `extra="forbid"` throughout: a mistyped key that silently does nothing is
    worse than a startup failure, because it looks like the setting took effect.
    `embedding` is the one loosely-typed field — a passthrough a host validates
    for itself; see the module docstring.
    """

    model_config = ConfigDict(extra="forbid")

    version: int
    providers: dict[str, ProviderSpec]
    defaults: RoleDefaults
    roles: dict[str, RoleSpec]
    embedding: dict[str, Any] | None = None

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

        return self
