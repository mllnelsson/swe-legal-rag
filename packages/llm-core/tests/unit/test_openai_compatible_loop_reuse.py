"""The provider driven the way a worker drives it: one event loop per message.

The unit tests in `test_clients.py` cover the cache; this covers the thing the
cache exists for. It talks to a loopback HTTP server rather than a mock, because
what broke was the connection pool underneath the SDK, which no mock has.

Before the fix this recorded one retry for every message after the first — the
shape the 2020-2026 ingest logged 219 times against 221 calls.
"""

from __future__ import annotations

import asyncio
import http.server
import logging
import socketserver
import threading
from collections.abc import Iterator

import pytest

from llm_core._clients import aclose_async_openai
from llm_core._config import LLMConfig, ProviderKind
from llm_core._types import Message, Role
from llm_core.providers._openai_compatible import OpenAiCompatibleProvider

MESSAGES = 4

_COMPLETION = (
    b'{"id":"1","object":"chat.completion","model":"stub",'
    b'"choices":[{"index":0,"message":{"role":"assistant","content":"ok"},'
    b'"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,'
    b'"total_tokens":2}}'
)


class _Handler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.1 so the connection is kept alive and actually pooled, which is the
    # precondition for the bug.
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(_COMPLETION)))
        self.end_headers()
        self.wfile.write(_COMPLETION)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence the per-request line stdlib writes straight to stderr."""


class _RetryCounter(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "Retrying request" in record.getMessage():
            self.count += 1


@pytest.fixture
def stub_host() -> Iterator[str]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def retries() -> Iterator[_RetryCounter]:
    counter = _RetryCounter()
    logger = logging.getLogger("openai._base_client")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(counter)
    try:
        yield counter
    finally:
        logger.removeHandler(counter)
        logger.setLevel(previous_level)


def test_a_message_per_loop_costs_no_retries(
    stub_host: str, retries: _RetryCounter
) -> None:
    # Built once, outside any loop, exactly as each worker's `subscribe()` does.
    provider = OpenAiCompatibleProvider(
        LLMConfig(
            provider=ProviderKind.OPENAI_COMPATIBLE,
            model="stub",
            api_key="stub-key",
            base_url=stub_host,
        )
    )

    async def one_message(index: int) -> str:
        """`shared.worker.subscribe_step`'s inner `run()`, minus the session.

        The `finally` is what `ai.close_llm_clients` is passed as `teardown` to
        do for a real worker.
        """
        try:
            response = await provider.generate(
                [Message(role=Role.user, content=str(index))]
            )
            return response.message.content
        finally:
            await aclose_async_openai()

    answers = [asyncio.run(one_message(index)) for index in range(MESSAGES)]

    assert answers == ["ok"] * MESSAGES
    assert retries.count == 0
