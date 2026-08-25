"""The request envelope: one line in, one line out, and what rides on them."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from ai import interaction_scope
from api.access_log import (
    PREVIEW_LIMIT,
    AccessLogMiddleware,
    format_duration,
    note,
    preview,
    render_fields,
)
from api.correlation import INTERACTION_ID_HEADER, interaction_id_of
from api.logging_setup import InteractionFilter

_LOGGER = "api.access"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)

    @app.get("/plain")
    def plain(request: Request) -> dict:
        note(request, hits=12, q="två ord")
        return {"ok": True}

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("induced")

    @app.get("/echo-id")
    def echo_id(request: Request) -> dict:
        return {"interaction_id": interaction_id_of(request)}

    @app.get("/stream")
    def stream(request: Request) -> StreamingResponse:
        def generate() -> Iterator[str]:
            for index in range(3):
                time.sleep(0.05)
                yield f"chunk {index}\n"
            note(request, chunks=3)

        return StreamingResponse(generate(), media_type="text/plain")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


def _access_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == _LOGGER and record.levelno >= logging.INFO
    ]


def test_one_entry_and_one_exit_line(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        client.get("/plain")

    entry, exit_line = _access_lines(caplog)
    assert entry.startswith("→ GET /plain interaction=")
    assert exit_line.startswith("← GET /plain 200 in ")


def test_route_metadata_lands_on_the_exit_line(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        client.get("/plain")

    exit_line = _access_lines(caplog)[-1]
    assert " hits=12" in exit_line
    # Quoted because it contains a space; unquoted it would read as two fields.
    assert ' q="två ord"' in exit_line


def test_the_exit_line_waits_for_the_whole_stream(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The reason this is a raw ASGI middleware and not `BaseHTTPMiddleware`.

    `BaseHTTPMiddleware` returns at first byte, which on `POST /api/chat` would
    report a fraction of a twenty-second turn and lose everything the route
    noted while streaming.
    """
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        response = client.get("/stream")
        assert response.status_code == 200

    exit_line = _access_lines(caplog)[-1]
    assert " chunks=3" in exit_line
    assert " aborted" not in exit_line


def test_quiet_paths_say_nothing_at_info(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        client.get("/healthz")
    assert _access_lines(caplog) == []


def test_quiet_paths_still_log_at_debug(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        client.get("/healthz")
    messages = [record.getMessage() for record in caplog.records]
    assert any(message.startswith("→ GET /healthz") for message in messages)
    assert any(message.startswith("← GET /healthz 200") for message in messages)


def test_an_escaping_exception_is_logged_once_and_still_pairs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        response = client.get("/boom")

    assert response.status_code == 500
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert errors[0].exc_info is not None

    messages = _access_lines(caplog)
    assert sum(message.startswith("→") for message in messages) == 1
    assert sum(message.startswith("←") for message in messages) == 1
    assert messages[-1].startswith("← GET /boom 500 in ")


def test_a_supplied_interaction_id_is_the_one_used(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    supplied = str(uuid.uuid4())
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        response = client.get("/echo-id", headers={INTERACTION_ID_HEADER: supplied})

    # The route reads the id the middleware resolved rather than minting a second
    # one, so the log line and the response agree.
    assert response.json()["interaction_id"] == supplied
    assert _access_lines(caplog)[0].endswith(f"interaction={supplied}")


def test_a_rejected_interaction_id_is_replaced_not_echoed(client: TestClient) -> None:
    response = client.get("/echo-id", headers={INTERACTION_ID_HEADER: "not-a-uuid"})
    resolved = response.json()["interaction_id"]
    assert resolved != "not-a-uuid"
    uuid.UUID(resolved)


def test_note_on_a_request_without_the_middleware_is_harmless() -> None:
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    note(request, hits=1)


class TestPreview:
    def test_leaves_short_text_alone(self) -> None:
        assert preview("hur många avslag 2026?") == "hur många avslag 2026?"

    def test_collapses_whitespace(self) -> None:
        assert preview("två\n  ord") == "två ord"

    def test_truncates_long_text(self) -> None:
        rendered = preview("a" * 500)
        assert rendered.endswith("…")
        assert len(rendered) == PREVIEW_LIMIT + 1


class TestRenderFields:
    def test_renders_key_value_pairs(self) -> None:
        assert (
            render_fields({"hits": 12, "expanded": False}) == " hits=12 expanded=False"
        )

    def test_quotes_values_that_would_split(self) -> None:
        assert render_fields({"q": "två ord"}) == ' q="två ord"'
        assert render_fields({"q": ""}) == ' q=""'

    def test_rounds_floats(self) -> None:
        assert render_fields({"top_sim": 0.8412}) == " top_sim=0.84"


class TestFormatDuration:
    def test_milliseconds_below_a_second(self) -> None:
        assert format_duration(0.0842) == "84ms"

    def test_seconds_above(self) -> None:
        assert format_duration(17.24) == "17.2s"


class TestInteractionFilter:
    def _record(self) -> logging.LogRecord:
        return logging.LogRecord(
            "test", logging.INFO, __file__, 1, "message", None, None
        )

    def test_carries_the_current_interaction(self) -> None:
        record = self._record()
        interaction_id = str(uuid.uuid4())
        with interaction_scope(interaction_id):
            InteractionFilter().filter(record)
        # Through __dict__, the way the filter writes it: LogRecord declares
        # no such field, so attribute access does not typecheck.
        assert record.__dict__["interaction"] == interaction_id[:8]

    def test_falls_back_outside_a_request(self) -> None:
        record = self._record()
        InteractionFilter().filter(record)
        assert record.__dict__["interaction"] == "-"
