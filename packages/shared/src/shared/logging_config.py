"""The one logging configuration every entry point in the repo applies.

Each worker used to call ``logging.basicConfig`` at *import* time, which made the
result depend on import order: ``scripts/run_pipeline.py`` imports six workers
before reaching its own ``basicConfig`` line, and ``basicConfig`` is a no-op once
the root logger has a handler — so the script's format was silently discarded and
a whole pipeline run logged without timestamps.

:func:`configure_logging` is called from ``main()`` rather than at import, and
passes ``force=True``, so the entry point that is actually running decides.

Named ``logging_config`` and not ``logging``: a ``shared/logging.py`` would read
as if the ``import logging`` above it were the local one.
"""

from __future__ import annotations

import logging
import os

from dotenv import dotenv_values, find_dotenv

__all__ = [
    "FORMAT",
    "LOG_LEVEL_ENV",
    "TIME_FORMAT",
    "configure_logging",
    "resolve_log_level",
]

# The timestamp is the point. A pipeline run is a long sequence of per-document
# steps, and "when did this start, how long did it take" is most of what the log
# is read for. The date is left out: a run is watched live, within one day.
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
TIME_FORMAT = "%H:%M:%S"

LOG_LEVEL_ENV = "LOG_LEVEL"

DEFAULT_LEVEL = logging.INFO


def resolve_log_level() -> int:
    """The level ``LOG_LEVEL`` asks for, or :data:`DEFAULT_LEVEL`.

    Read from the process environment first, then from ``.env`` directly. The
    second lookup exists because every entry point in this repo calls
    :func:`configure_logging` *before* ``load_dotenv()`` — and in most workers
    ``load_dotenv()`` is not even in ``main()``, it is inside ``subscribe()``.
    Reordering them to suit one variable would move every other variable's load
    point too; reading one key out of the file does not. ``dotenv_values`` is
    read-only and puts nothing into ``os.environ``, so nobody else's resolution
    order changes.

    An unparseable value raises. This module exists because a logging
    configuration was once *silently* discarded, and quietly serving INFO to
    someone who asked for DEBUG is that same failure — see ``ChatScript`` in
    ``api.config`` for the same fail-at-startup stance on a typed env var.
    """
    raw = os.environ.get(LOG_LEVEL_ENV) or _from_dotenv()
    if raw is None:
        return DEFAULT_LEVEL

    level = logging.getLevelNamesMapping().get(raw.strip().upper())
    if level is None:
        accepted = ", ".join(
            name for name in logging.getLevelNamesMapping() if name != "NOTSET"
        )
        raise ValueError(
            f"{LOG_LEVEL_ENV}={raw!r} is not a logging level; use one of: {accepted}"
        )
    return level


def configure_logging(level: int | None = None) -> None:
    """Install the shared root handler, replacing anything already configured.

    ``level=None`` — what every caller passes — resolves ``LOG_LEVEL``. An
    explicit level still wins, so the parameter keeps the meaning it had.
    """
    resolved = resolve_log_level() if level is None else level
    logging.basicConfig(level=resolved, format=FORMAT, datefmt=TIME_FORMAT, force=True)


def _from_dotenv() -> str | None:
    path = find_dotenv(usecwd=True)
    if not path:
        return None
    return dotenv_values(path).get(LOG_LEVEL_ENV)
