"""Loading the config document and resolving a role to an `llm_core.LLMConfig`.

**Precedence** (highest first): environment variable, then the role's own entry,
then `defaults`, then the field default on `llm_core.LLMConfig`. The file is the
checked-in default; the environment is the deployment override. Note this is the
opposite of pydantic-settings' native ordering — see `without_env_overrides`.

API keys are never read from the file. A provider names the environment variable
holding its key; the value stays in `.env` or a secret manager.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings

from llm_core import LLMConfig, ProviderKind

from agent_kit.config._document import (
    CONFIG_FILENAME,
    CONFIG_PATH_ENV,
    LLMConfigDocument,
    ProviderSpec,
    RoleSpec,
)
from agent_kit.errors import (
    LLMConfigInvalidError,
    LLMConfigNotFoundError,
    UnknownLLMRoleError,
)

logger = logging.getLogger(__name__)

# Per-role model override, e.g. LLM_MODEL_CHAT. A role added to the config gets
# its own override name for free.
_ROLE_MODEL_ENV_TEMPLATE = "LLM_MODEL_{role}"


def find_config_path() -> Path:
    """Locate the config document.

    `LLM_CONFIG_PATH` wins if set. Otherwise walk up from the working directory:
    in a uv workspace, tests are routinely run from a package subdirectory where
    the repo root is not the cwd.
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
            f"{path} must contain a YAML mapping at the top level, "
            f"got {type(raw).__name__}"
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
    """Build the `llm_core.LLMConfig` for a named role, applying precedence.

    `role` is a plain string because this resolves a key out of the file, where
    role names are arbitrary. A host that wants a closed set of role names keeps
    an enum one layer up — the same split as a provider's `kind` (a
    `ProviderKind`) versus the name the file gives it.
    """
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
        "api_key": api_key_for(provider),
        "temperature": _first_set(spec.temperature, defaults.temperature),
        "max_tokens": _first_set(spec.max_tokens, defaults.max_tokens),
        "stream_usage": _first_set(spec.stream_usage, defaults.stream_usage),
    }

    # `model` is passed unconditionally rather than through the helper: its own
    # env alias is the pre-roles global LLM_MODEL, and letting that through would
    # collapse every role onto one model. The per-role name is the override.
    return LLMConfig(
        model=os.environ.get(role_model_env_var(role), spec.model),
        **without_env_overrides(LLMConfig, inherited),
    )


def role_model_env_var(role: str) -> str:
    """The environment variable that overrides a role's model."""
    return _ROLE_MODEL_ENV_TEMPLATE.format(role=role.upper().replace("-", "_"))


def api_key_for(provider: ProviderSpec) -> str | None:
    """The key value for a provider entry, read from the variable it names.

    `api_key_env` is unset only for `kind: none`, which has no host to send a
    key to — see `ProviderSpec._check_api_key_env`.
    """
    if provider.api_key_env is None:
        return None
    return os.environ.get(provider.api_key_env)


def _first_set[T](override: T | None, fallback: T) -> T:
    return fallback if override is None else override


def _warn_if_env_masks_role_provider(
    role: str, spec: RoleSpec, kind: ProviderKind
) -> None:
    """Say so when LLM_PROVIDER overrides a provider the role asked for by name.

    LLM_PROVIDER is process-wide and pre-dates per-role providers, so a stale one
    in `.env` silently flattens every role onto one host — and the config still
    reads as though the per-role choice is in effect. Env winning is intended;
    doing it invisibly is not.
    """
    env_provider = os.environ.get(env_alias(LLMConfig, "provider"))
    if spec.provider is None or env_provider is None or env_provider == kind:
        return

    logger.warning(
        "Role %r declares provider %r (kind %s) in %s, but %s=%s is set in the "
        "environment and takes precedence. Unset it to let the file decide.",
        role,
        spec.provider,
        kind.value,
        CONFIG_FILENAME,
        env_alias(LLMConfig, "provider"),
        env_provider,
    )


def without_env_overrides(
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
        if env_alias(settings_type, name) not in os.environ
    }


def env_alias(settings_type: type[BaseSettings], field_name: str) -> str:
    """The environment variable a settings field reads, taken from the model itself.

    Read off the field rather than restated here, so the two can't disagree.
    """
    alias = settings_type.model_fields[field_name].alias
    return alias if alias is not None else field_name.upper()
