"""What `run_agent` yields as it works — a domain-free progress stream.

These carry no vocabulary of any one corpus: a tool is a `name` and `arguments`,
evidence is an opaque `E`, an error is a message. A host maps this stream onto
its own richer events (labels, source references, a SQL trail) as it consumes
it. `DoneEvent` and `ErrorEvent` are terminal, and an `ErrorEvent` is never
followed by a `DoneEvent`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolStatus(StrEnum):
    """How a tool call came back."""

    OK = "ok"
    # The tool declined on policy — an ungrounded filter, a budget reached. Not
    # a failure: the loop repairs itself from it.
    REFUSED = "refused"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PlanReplyEvent:
    """The plan step answered directly, without handing work to the executor.

    A greeting, a thank-you, a follow-up the history already answers. The reply
    is whole, not streamed — for a sentence or two that costs nothing and saves
    the executor loop entirely.
    """

    text: str


@dataclass(frozen=True, slots=True)
class ToolCallEvent:
    """The executor asked for a tool; the executor function has not run yet."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResultEvent:
    """A tool executor returned. `result` is whatever it returned, unserialized.

    Carries the call's `arguments` as well as its result, so a host can label a
    result the same way it labelled the call without keeping its own bookkeeping.
    """

    id: str
    name: str
    arguments: dict[str, Any]
    status: ToolStatus
    result: Any


@dataclass(frozen=True, slots=True)
class EvidenceEvent[E]:
    """The evidence the executor selected, emitted once before synthesis streams.

    An ordering seam: a host that renders citations resolves them here, before
    the first answer token that may reference one.
    """

    evidence: E


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """One token of the synthesized answer."""

    text: str


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """The run finished cleanly. Terminal."""


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """The run failed. Terminal, and never followed by a `DoneEvent`.

    The message is a generic, safe-to-surface string; a host that wants its own
    wording replaces it when mapping.
    """

    message: str


AgentEvent = (
    PlanReplyEvent
    | ToolCallEvent
    | ToolResultEvent
    | EvidenceEvent[Any]
    | TokenEvent
    | DoneEvent
    | ErrorEvent
)
