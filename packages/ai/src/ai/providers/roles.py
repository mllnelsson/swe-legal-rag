"""Per-task LLM provider construction.

`llm_core.LLMConfig` carries a single `model` — one process-wide model for every
call. This project wants a different model per task, and sometimes a different
*provider* per task, so the assignment lives in `llm_config.yaml` under `roles`
and is resolved by `ai.llm_config`.

A role is just a name. Declaring one in the YAML is enough to use it; the three
constants below exist because they have call sites, not because the set is
closed. See documentation/reference/llm-config.md.

Each composition root constructs the role-appropriate provider(s) once at startup
and threads them into the call sites via the `provider=` keyword — there is no
hidden global default in production.
"""

from __future__ import annotations

from llm_core import LLMProvider, create_provider

from ai.llm_config import LLMConfigDocument, resolve_role_config

ROLE_STRUCTURED = "structured"
ROLE_SUMMARIZE = "summarize"
ROLE_CHAT = "chat"


def create_llm_provider(
    role: str, document: LLMConfigDocument | None = None
) -> LLMProvider:
    """Build the provider `llm_config.yaml` assigns to `role`.

    Raises `UnknownLLMRoleError` if the role is not declared.
    """
    return create_provider(resolve_role_config(role, document))


def create_structured_llm_provider() -> LLMProvider:
    return create_llm_provider(ROLE_STRUCTURED)


def create_summarize_llm_provider() -> LLMProvider:
    return create_llm_provider(ROLE_SUMMARIZE)


def create_chat_llm_provider() -> LLMProvider:
    return create_llm_provider(ROLE_CHAT)
