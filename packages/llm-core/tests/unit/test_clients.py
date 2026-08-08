"""The client must not outlive the event loop whose connections it pooled.

`shared.worker` runs `asyncio.run` once per queue message. A client built once
at process start therefore hands the second message a connection belonging to a
loop that has closed; that attempt fails instantly and the SDK retries, which is
what produced 219 retries against 221 calls on the 2020-2026 ingest.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from llm_core import _clients

API_KEY = "test-key"
BASE_URL = "https://api.example.test/v1"


class _FakeAsyncOpenAI:
    """Stands in for the SDK client, counting how often one is built."""

    instances: list[_FakeAsyncOpenAI] = []

    def __init__(self, *, api_key: str, base_url: str | None) -> None:
        self.api_key = api_key
        self.base_url = base_url
        _FakeAsyncOpenAI.instances.append(self)


@pytest.fixture(autouse=True)
def fake_sdk(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_FakeAsyncOpenAI]]:
    import openai

    _FakeAsyncOpenAI.instances = []
    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    _clients._clients.clear()
    yield _FakeAsyncOpenAI
    _clients._clients.clear()


def _get() -> Any:
    return _clients.get_async_openai(api_key=API_KEY, base_url=BASE_URL)


async def _get_twice() -> tuple[Any, Any]:
    return _get(), _get()


def test_one_client_is_reused_within_a_loop(
    fake_sdk: type[_FakeAsyncOpenAI],
) -> None:
    """The API server holds one loop for its lifetime; it must keep keep-alive."""
    first, second = asyncio.run(_get_twice())

    assert first is second
    assert len(fake_sdk.instances) == 1


def test_a_new_loop_gets_its_own_client(fake_sdk: type[_FakeAsyncOpenAI]) -> None:
    """One `asyncio.run` per queue message must not share a connection pool."""

    async def _get_one() -> Any:
        return _get()

    first = asyncio.run(_get_one())
    second = asyncio.run(_get_one())

    assert first is not second
    assert len(fake_sdk.instances) == 2


def test_clients_for_closed_loops_are_discarded() -> None:
    """Otherwise a backfill leaks one client, and its socket, per message."""

    async def _get_one() -> Any:
        return _get()

    for _ in range(5):
        asyncio.run(_get_one())

    assert len(_clients._clients) == 1


def test_different_credentials_do_not_share_a_client(
    fake_sdk: type[_FakeAsyncOpenAI],
) -> None:
    """A worker with two roles on two hosts must not send one's key to the other."""

    async def _get_both() -> tuple[Any, Any]:
        return (
            _clients.get_async_openai(api_key=API_KEY, base_url=BASE_URL),
            _clients.get_async_openai(api_key="other-key", base_url=BASE_URL),
        )

    first, second = asyncio.run(_get_both())

    assert first is not second
    assert [instance.api_key for instance in fake_sdk.instances] == [
        API_KEY,
        "other-key",
    ]


def test_credentials_reach_the_sdk(fake_sdk: type[_FakeAsyncOpenAI]) -> None:
    asyncio.run(_get_twice())

    (instance,) = fake_sdk.instances
    assert instance.api_key == API_KEY
    assert instance.base_url == BASE_URL


def test_calling_outside_a_loop_is_refused() -> None:
    """The binding is to the *running* loop, so there has to be one."""
    with pytest.raises(RuntimeError, match="no running event loop"):
        _get()
