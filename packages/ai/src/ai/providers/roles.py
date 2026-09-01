"""Per-task LLM provider construction.

`agent_kit.llm.LLMConfig` carries a single `model` — one process-wide model for every
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

# The role-to-provider machinery is domain-free and now lives in agent-kit;
# `create_llm_provider` and `llm_role_is_disabled` take a plain role-name string.
# This module keeps the closed set of role *names* this project assigns models
# to, so a misspelled role is a type error here rather than a runtime miss. An
# `LLMRole` member is a `str`, so it flows straight into the agent-kit functions.
from agent_kit.config import create_llm_provider, llm_role_is_disabled

__all__ = ["LLMRole", "create_llm_provider", "llm_role_is_disabled"]


class LLMRole(StrEnum):
    """The tasks this project assigns models to.

    Values match the keys under `roles:` in `llm_config.yaml`.
    """

    STRUCTURED = auto()
    SUMMARIZE = auto()
    CHAT = auto()
    ORCHESTRATE = auto()
    SQL = auto()
    READ = auto()
