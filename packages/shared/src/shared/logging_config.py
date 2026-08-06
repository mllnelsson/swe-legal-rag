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

__all__ = ["configure_logging"]

# The timestamp is the point. A pipeline run is a long sequence of per-document
# steps, and "when did this start, how long did it take" is most of what the log
# is read for. The date is left out: a run is watched live, within one day.
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_TIME_FORMAT = "%H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    """Install the shared root handler, replacing anything already configured."""
    logging.basicConfig(level=level, format=_FORMAT, datefmt=_TIME_FORMAT, force=True)
