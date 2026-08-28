"""Correlation scopes for a unit of work — moved to `agent_kit.tracing`.

Kept here as a re-export so existing `ai` call sites (`api.main`, the chat
agent) and `ai.__init__` keep importing from where they always have. The
definitions are domain-free and now live in the agent core.
"""

from __future__ import annotations

from agent_kit.tracing import agent_run_scope, interaction_scope

__all__ = ["agent_run_scope", "interaction_scope"]
