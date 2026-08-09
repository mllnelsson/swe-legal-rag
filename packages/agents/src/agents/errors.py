"""Domain errors for the agents package."""

from __future__ import annotations


class AgentError(Exception):
    """Base class for all agents package errors."""


class SqlRejectedError(AgentError):
    """The guard refused to execute a generated statement.

    Carries the reason in a form meant to be handed straight back to the model:
    the loop turns a rejection into a `tool_result`, not a failure, so the model
    can repair its query on the next iteration. That is why this is raised inside
    the tool executor and caught there rather than escaping to the caller.
    """


class SemanticModelNotFoundError(AgentError):
    """`semantic_model.yaml` is not where it should be.

    Fatal rather than recoverable: the file supplies the agent's table
    allow-list and its grounding policy, so there is no reduced mode to fall
    back to.
    """


class SemanticModelInvalidError(AgentError):
    """`semantic_model.yaml` could not be read or does not match its schema."""


class SemanticModelIncompleteError(AgentError):
    """The semantic model and the ORM disagree about what the database holds.

    The schema handed to the model is generated from SQLAlchemy metadata but its
    prose comes from the YAML, so a column added by a migration would otherwise
    reach the prompt as a bare name and type — and for a column like
    `decision_outcome` the prose is exactly what stops it being misused. Raised
    for drift in either direction: a described column that no longer exists, and
    an existing column nobody described.
    """
