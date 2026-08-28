"""Per-task LLM provider construction.

`llm_core.LLMConfig` carries a single `model` — one process-wide model for every
call. An agent app usually wants a different model per task, and sometimes a
different *provider* per task, so the assignment lives in the config document
under `roles` and is resolved by `resolve_role_config`.

`role` is a plain string here: it names a key in the file. A host that wants a
misspelled role to be a type error keeps a closed enum of role names one layer
up and passes its members in — a `StrEnum` member is a `str`, so it flows
through unchanged.

Each composition root constructs the role-appropriate provider(s) once at
startup and threads them into the call sites via the `provider=` keyword.
"""

from __future__ import annotations

from llm_core import LLMProvider, ProviderKind, create_provider

from agent_kit.config._document import LLMConfigDocument
from agent_kit.config._loader import resolve_role_config

__all__ = ["create_llm_provider", "llm_role_is_disabled"]


def create_llm_provider(
    role: str, document: LLMConfigDocument | None = None
) -> LLMProvider:
    """Build the provider the config document assigns to `role`.

    Raises `UnknownLLMRoleError` if the file declares no such role.
    """
    return create_provider(resolve_role_config(role, document))


def llm_role_is_disabled(
    role: str, document: LLMConfigDocument | None = None
) -> bool:
    """Whether the config assigns `role` no model at all — `kind: none`.

    For the callers that have a genuine no-model path and want to choose it at
    startup, where every other provider decision is made. Everyone else should
    just build the provider: constructing a `none` one always succeeds, and it
    raises `LLMDisabledError` at the call that wanted a model.
    """
    return resolve_role_config(role, document).provider is ProviderKind.NONE
