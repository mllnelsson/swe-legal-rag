"""Per-task LLM provider construction.

`llm_core.LLMConfig` carries a single `model` — one process-wide model for every
call. This project wants a different model per task, and sometimes a different
*provider* per task, so the assignment lives in `llm_config.yaml` under `roles`
and is resolved by `ai.llm_config`.

A role has two halves that must agree: an `LLMRole` member here, which is what
code asks for, and an entry under `roles:` in the YAML, which says what that
resolves to. Adding a task means adding both. The enum is what makes a
misspelled role a type error instead of a runtime one, and what lets
`create_llm_provider` be a single function rather than one wrapper per task.

Each composition root constructs the role-appropriate provider(s) once at
startup and threads them into the call sites via the `provider=` keyword — there
is no hidden global default in production.
"""

from __future__ import annotations

from enum import StrEnum, auto

from llm_core import LLMProvider, ProviderKind, create_provider

from ai.llm_config import LLMConfigDocument, resolve_role_config

__all__ = ["LLMRole", "create_llm_provider", "llm_role_is_disabled"]


class LLMRole(StrEnum):
    """The tasks this project assigns models to.

    Values match the keys under `roles:` in `llm_config.yaml`.
    """

    STRUCTURED = auto()
    SUMMARIZE = auto()
    CHAT = auto()


def create_llm_provider(
    role: LLMRole, document: LLMConfigDocument | None = None
) -> LLMProvider:
    """Build the provider `llm_config.yaml` assigns to `role`.

    Raises `UnknownLLMRoleError` if the file declares no such role.
    """
    return create_provider(resolve_role_config(role, document))


def llm_role_is_disabled(
    role: LLMRole, document: LLMConfigDocument | None = None
) -> bool:
    """Whether `llm_config.yaml` assigns `role` no model at all — `kind: none`.

    For the callers that have a genuine no-model path and want to choose it at
    startup, where every other provider decision is made. Everyone else should
    just build the provider: constructing a `none` one always succeeds, and it
    raises `LLMDisabledError` at the call that wanted a model.
    """
    return resolve_role_config(role, document).provider is ProviderKind.NONE
