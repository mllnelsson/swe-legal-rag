"""Per-conversation carry-over: a JSON blob a turn reads and the next turn writes.

The point is the follow-up. A conversation's first turn starts from nothing; a
later turn should be able to build on what earlier turns established without
redoing the work. The orchestrator injects this blob into the *first* LLM call
of every turn — the planning step — so the planner sees the running state before
it decides what, if anything, to gather. It is `{}` on the first turn, and a
turn may hand back an updated blob to persist.

What goes in the blob is the host's choice; this layer only moves it. The store
is a `Protocol` so a host can back it with a database, a cache, or the in-memory
implementation here, without the orchestrator knowing which.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# A conversation's carry-over. Opaque to this layer: the host decides its shape,
# and it must survive a round-trip through JSON, since a durable store will
# serialize it.
JsonBlob = dict[str, Any]


@runtime_checkable
class ContextStore(Protocol):
    """Reads and writes one conversation's carry-over blob by id."""

    async def get(self, conversation_id: str) -> JsonBlob:
        """The stored blob for `conversation_id`, or `{}` when there is none."""
        ...

    async def set(self, conversation_id: str, blob: JsonBlob) -> None:
        """Replace the stored blob for `conversation_id`."""
        ...


class InMemoryContextStore:
    """A `ContextStore` kept in a dict — for tests, scripts, and single-process runs.

    Copies on the way in and out, so a caller that mutates a blob it got from
    `get` (or one it passed to `set`) cannot reach back into the store. Async
    like the Protocol it satisfies, so a durable store is a drop-in replacement.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, JsonBlob] = {}

    async def get(self, conversation_id: str) -> JsonBlob:
        return dict(self._by_id.get(conversation_id, {}))

    async def set(self, conversation_id: str, blob: JsonBlob) -> None:
        self._by_id[conversation_id] = dict(blob)
