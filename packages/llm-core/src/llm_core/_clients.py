"""One OpenAI SDK client per running event loop.

This is `shared.db`'s treatment of the asyncpg engine applied to the `httpx`
connection pool inside `AsyncOpenAI`, and for the same reason: a pooled
connection belongs to the loop that opened it.

`shared.worker` calls ``asyncio.run`` once per queue message, so a client built
once at process start hands the *second* message a connection whose loop has
since closed. That attempt fails instantly — no HTTP status, no response — and
the SDK's generic ``except Exception -> retry`` in ``_base_client.request``
hides it behind a retry that succeeds on a fresh connection, which is then
pooled for the next dead loop. The 2020-2026 ingest logged **219 retries against
221 calls**, every one the SDK's first retry, every response ``200 OK``: a wasted
round trip plus ~0.44 s of backoff on every LLM call the pipeline made.

Keeping the client with the loop fixes that without giving up connection reuse
where it is worth having. A process with one long-lived loop — the API server —
builds one client and keeps its pool, exactly as before; a worker pays one
handshake per message, which it was already paying *after* the wasted attempt.

Whoever owns a loop for one unit of work must call :func:`aclose_async_openai`
before it closes, exactly as they already call `shared.db.dispose_async_engine`.
Skipping it does not leak — :func:`get_async_openai` drops entries whose loop is
gone — but it is noisy: `AsyncOpenAI.__del__` schedules `aclose()` on *whatever
loop is running when the garbage collector gets to it*, and that coroutine then
touches a transport belonging to the loop that closed, logging an unretrieved
`RuntimeError: Event loop is closed` per discarded client.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from openai import AsyncOpenAI

__all__ = ["aclose_async_openai", "get_async_openai"]


class _ClientKey(NamedTuple):
    """What makes two callers able to share a client: a loop and a destination."""

    loop: asyncio.AbstractEventLoop
    api_key: str
    base_url: str | None


_clients: dict[_ClientKey, AsyncOpenAI] = {}


def get_async_openai(*, api_key: str, base_url: str | None) -> AsyncOpenAI:
    """The client for these credentials, bound to the loop running now.

    Must be called from inside the loop that will make the request — that is the
    whole point — so providers call it per request rather than in ``__init__``.
    """
    from openai import AsyncOpenAI

    _discard_closed_loops()

    key = _ClientKey(asyncio.get_running_loop(), api_key, base_url)
    client = _clients.get(key)
    if client is None:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        _clients[key] = client
    return client


async def aclose_async_openai() -> None:
    """Close the running loop's clients and the connections they pooled.

    Any caller that owns a loop for one unit of work must call this before the
    loop closes — the counterpart to `shared.db.dispose_async_engine`, and for
    the same reason. Doing it here, while the loop is still running, is the only
    point at which the close can actually reach the sockets it owns.
    """
    loop = asyncio.get_running_loop()
    for key in [key for key in _clients if key.loop is loop]:
        await _clients.pop(key).close()


def _discard_closed_loops() -> None:
    """Backstop for a caller that never called :func:`aclose_async_openai`.

    There is no graceful close to await here — the loop it would need has gone —
    so this only stops the cache growing by one entry per message. The noisy
    teardown described in the module docstring is the cost of reaching it.
    """
    for key in [key for key in _clients if key.loop.is_closed()]:
        del _clients[key]
