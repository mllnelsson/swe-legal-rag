"""The in-memory context store: round-trips a blob and isolates its copies."""

from __future__ import annotations

from agent_kit import InMemoryContextStore


async def test_absent_conversation_reads_as_empty() -> None:
    store = InMemoryContextStore()
    assert await store.get("never-seen") == {}


async def test_set_then_get_round_trips() -> None:
    store = InMemoryContextStore()
    await store.set("c1", {"turns": 2, "topic": "x"})
    assert await store.get("c1") == {"turns": 2, "topic": "x"}


async def test_get_returns_a_copy() -> None:
    """Mutating what `get` returned must not reach back into the store."""
    store = InMemoryContextStore()
    await store.set("c1", {"turns": 1})

    got = await store.get("c1")
    got["turns"] = 99

    assert await store.get("c1") == {"turns": 1}


async def test_set_copies_its_input() -> None:
    """Mutating the blob after `set` must not change what was stored."""
    store = InMemoryContextStore()
    blob = {"turns": 1}
    await store.set("c1", blob)

    blob["turns"] = 99

    assert await store.get("c1") == {"turns": 1}


async def test_conversations_are_independent() -> None:
    store = InMemoryContextStore()
    await store.set("a", {"n": 1})
    await store.set("b", {"n": 2})
    assert await store.get("a") == {"n": 1}
    assert await store.get("b") == {"n": 2}
