"""Errors raised by the agent core."""

from __future__ import annotations


class AgentKitError(Exception):
    """Base class for all agent-kit errors."""


class LLMConfigError(AgentKitError):
    """Base class for problems with the LLM config document."""


class LLMConfigNotFoundError(LLMConfigError):
    """No config document could be located.

    Deliberately fatal rather than falling back to built-in defaults: a silent
    fallback is how the documented model set and the one actually in use drift
    apart.
    """


class LLMConfigInvalidError(LLMConfigError):
    """The config document was found but is malformed or internally inconsistent."""


class UnknownLLMRoleError(LLMConfigError):
    """A provider was requested for a role the config document does not declare."""
