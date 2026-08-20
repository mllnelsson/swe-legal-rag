"""Process-wide logging configuration for the API.

The API is the one entry point in this repo with no ``main()`` — ``uvicorn
api.main:app`` makes the *import* of ``api.main`` the entry point, so this runs
at import there rather than from a function. That does not reopen the import-order
problem ``shared.logging_config`` documents: nothing imports ``api.main`` except
uvicorn and the tests, so there is no second entry point to fight with.

Three things happen here that ``configure_logging()`` alone does not do:

- uvicorn's own loggers are adopted, so one process logs in one format;
- ``uvicorn.access`` is silenced, because :mod:`api.access_log` already logs every
  request with strictly more detail;
- every record gets the request's ``interaction_id``, so concurrent requests can be
  told apart and a line can be joined to the [trace directory](/observability.md)
  holding that turn's prompts.
"""

from __future__ import annotations

import logging

from llm_core import current_trace_context

from shared.logging_config import TIME_FORMAT, configure_logging, resolve_log_level

__all__ = ["INTERACTION_WIDTH", "InteractionFilter", "configure_api_logging"]

# Enough of a uuid4 to be unique among the handful of requests in flight at once,
# short enough to be a column rather than a line.
INTERACTION_WIDTH = 8

# Stands in when a record is logged outside any request — startup, shutdown, a
# background task. A fixed-width placeholder keeps the column aligned.
_NO_INTERACTION = "-"

# Only used at DEBUG. At INFO the id is already on the access `→` line and once
# per request is enough; at DEBUG the per-step lines interleave and the column is
# the only thing that untangles them.
_DEBUG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(interaction)s]: %(message)s"

# uvicorn installs its own colourised handlers on these and sets propagate=False,
# which is what makes `Started server process` arrive in a different shape from
# every application line.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Libraries that log one line per HTTP call, per cached file, or per tensor. At
# INFO they would outnumber this system's own lines several to one; at DEBUG they
# are a wall. "Let me see each step" means this system's steps — a third party's
# are one level further down, and are reached by naming its logger directly.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "openai",
    "filelock",
    "transformers",
    "sentence_transformers",
)


class InteractionFilter(logging.Filter):
    """Put the current interaction id on every record reaching the handler.

    Reads the LLM trace context rather than a ContextVar of its own: the access
    middleware opens ``ai.interaction_scope`` around the whole request, so that
    context is already populated for every record the request produces — including
    ones from ``agents`` and ``ai``, which know nothing about this module.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        interaction = current_trace_context().get("interaction_id")
        # Assigned through __dict__ because that is what `logging` itself does
        # when it merges `extra=`, and because LogRecord declares no such field.
        record.__dict__["interaction"] = (
            str(interaction)[:INTERACTION_WIDTH] if interaction else _NO_INTERACTION
        )
        return True


def configure_api_logging() -> None:
    """Install the root handler, adopt uvicorn's loggers, add the id column."""
    level = resolve_log_level()
    configure_logging(level)

    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(InteractionFilter())
        if level <= logging.DEBUG:
            handler.setFormatter(logging.Formatter(_DEBUG_FORMAT, datefmt=TIME_FORMAT))

    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # Not disabled — a failure to write an access line still deserves to surface.
    # Silenced at INFO because `api.access` says the same thing and more.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Damped one step rather than silenced, so turning the knob to DEBUG still
    # gains something from them without drowning what it was turned for.
    third_party_level = logging.INFO if level <= logging.DEBUG else logging.WARNING
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(third_party_level)
