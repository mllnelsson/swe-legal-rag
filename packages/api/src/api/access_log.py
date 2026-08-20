"""One line in, one line out, for every HTTP request.

The API had no request logging at all, which made a slow chat turn and a hung one
look identical from the outside. This is the API's answer to
``shared.pipeline.run_pipeline_step``: the envelope owns entry, exit, duration and
outcome, and each route adds only what is specific to its own work, via
:func:`note`. A route never logs its own started/finished pair.

**Why raw ASGI and not ``BaseHTTPMiddleware``.** ``BaseHTTPMiddleware`` hands back
control as soon as the response *starts*, so on ``POST /api/chat`` its exit line
would report time to first byte — a few hundred milliseconds of a twenty-second
turn. Wrapping ``send`` instead lets this see the terminating
``http.response.body`` with ``more_body`` false, which for an SSE stream is the
real end of the answer.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ai import interaction_scope
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.correlation import INTERACTION_ID_HEADER, resolve_interaction_id

__all__ = ["AccessLogMiddleware", "PREVIEW_LIMIT", "note", "preview", "render_fields"]

logger = logging.getLogger("api.access")

# Free text never reaches a log line whole. The payloads live in the trace files
# (/observability.md); the log carries just enough to recognise which request a
# line belongs to.
PREVIEW_LIMIT = 120

# Logged at DEBUG rather than INFO. A liveness probe every few seconds otherwise
# buries the one request anybody wanted to read about.
_QUIET_PATHS = frozenset({"/healthz"})

_STATE_FIELDS = "log_fields"
_STATE_INTERACTION = "interaction_id"


def preview(text: str, *, limit: int = PREVIEW_LIMIT) -> str:
    """Shorten free text to something safe to put in a log line."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit] + "…"


def note(request: Request, **fields: Any) -> None:
    """Contribute metadata to this request's exit line.

    Goes through ``request.scope`` rather than ``request.state`` so that calling
    it on a request built without this middleware is a no-op rather than an
    ``AttributeError`` — services and routes are called directly from tests.
    """
    state = request.scope.setdefault("state", {})
    state.setdefault(_STATE_FIELDS, {}).update(fields)


def render_fields(fields: dict[str, Any]) -> str:
    """``{"hits": 12, "q": "två ord"}`` -> `` hits=12 q="två ord"``."""
    parts = []
    for key, value in fields.items():
        rendered = f"{value:.2f}" if isinstance(value, float) else str(value)
        if not rendered or any(character.isspace() for character in rendered):
            rendered = f'"{rendered}"'
        parts.append(f" {key}={rendered}")
    return "".join(parts)


def format_duration(seconds: float) -> str:
    """Milliseconds below a second, seconds above.

    A browse endpoint answers in single-digit milliseconds and a chat turn takes
    twenty seconds; one fixed precision cannot read well for both.
    """
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.1f}s"


class AccessLogMiddleware:
    """Log every HTTP request's arrival, outcome, duration and route metadata.

    Invariant: **exactly one ``←`` for every ``→``**. The exit line is emitted
    from a ``finally``, so it survives an exception, a client disconnect and an
    abandoned SSE stream alike. An exception additionally gets its own ERROR
    record with the traceback, and is re-raised — Starlette's own
    ``ServerErrorMiddleware`` sits outside this one and still produces the 500.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope["method"]
        path: str = scope["path"]
        level = logging.DEBUG if path in _QUIET_PATHS else logging.INFO

        headers = Headers(scope=scope)
        interaction_id = resolve_interaction_id(headers.get(INTERACTION_ID_HEADER))

        fields: dict[str, Any] = {}
        state = scope.setdefault("state", {})
        state[_STATE_INTERACTION] = interaction_id
        state[_STATE_FIELDS] = fields

        status = 500
        completed = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status, completed
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                completed = True
            await send(message)

        # Opened here so that every record the request produces — this module's,
        # the routes', and `agents`/`ai`'s — carries the same id, and so that the
        # LLM traces of a request that never touches `interaction_scope` itself
        # (search, for one) are keyed by the id the client was given.
        with interaction_scope(interaction_id):
            logger.log(level, "→ %s %s interaction=%s", method, path, interaction_id)
            if scope.get("query_string"):
                logger.debug(
                    "  query %s", preview(scope["query_string"].decode("latin-1"))
                )

            started_at = time.perf_counter()
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                logger.exception(
                    "✗ %s %s failed after %s",
                    method,
                    path,
                    format_duration(time.perf_counter() - started_at),
                )
                raise
            finally:
                logger.log(
                    level,
                    "← %s %s %d in %s%s%s",
                    method,
                    path,
                    status,
                    format_duration(time.perf_counter() - started_at),
                    render_fields(fields),
                    "" if completed else " aborted",
                )
