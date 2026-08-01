"""Runs the whole ingestion pipeline — crawl through embed — in one process.

Why this exists: with ``QUEUE_BACKEND=sync`` a publish is a direct call into the
handler registered for that topic *in the same process*, and the broker backing
it (``shared.queue.factory``) is a module-level singleton. A handler registered
in another process is therefore invisible, which is why ``python -m
worker_crawl`` on its own fails with ``QueueHandlerError: No handler registered
for topic: 'download'`` — nothing ever subscribed.

The fix is to register the six downstream handlers first and then let crawl
cascade into them. Each worker exposes ``subscribe()`` for exactly this: it
builds the worker's wiring, registers its handler and returns without blocking.
Composing the pipeline is calling those in order and running crawl last.

This is what the ``pipeline`` container runs — see /playbooks/local-dev.md.
For iterating on one step at a time instead, use ``scripts/run_step.py``.

Usage (from the repo root, with .env configured):

    uv run python scripts/run_pipeline.py                    # current year
    uv run python scripts/run_pipeline.py --years all        # full backfill
    uv run python scripts/run_pipeline.py --years 2019-2021  # a range
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from dotenv import load_dotenv

from shared.config import QueueBackendType, get_settings
from shared.queue.base import QueueSubscriber
from worker_chunk.__main__ import subscribe as subscribe_chunk
from worker_crawl.__main__ import main as run_crawl
from worker_download.__main__ import subscribe as subscribe_download
from worker_embed.__main__ import subscribe as subscribe_embed
from worker_extract.__main__ import subscribe as subscribe_extract
from worker_metadata.__main__ import subscribe as subscribe_metadata
from worker_parse.__main__ import subscribe as subscribe_parse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("run_pipeline")

# Every step downstream of crawl, in pipeline order. Each registers its handler
# on the shared sync broker and returns the subscriber without starting it —
# starting is `shared.worker.serve`'s job, and this script never calls it.
_SUBSCRIBING_WORKERS: tuple[Callable[[], QueueSubscriber], ...] = (
    subscribe_download,
    subscribe_parse,
    subscribe_metadata,
    subscribe_extract,
    subscribe_chunk,
    subscribe_embed,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_pipeline",
        description="Run crawl through embed in a single process (sync queue).",
    )
    parser.add_argument(
        "--years",
        default=None,
        help=(
            "Which decision years to crawl: 'current' (default), 'all', '2019', "
            "'2019-2021', or a comma-separated mix. Overrides CRAWL_YEARS."
        ),
    )
    return parser.parse_args(argv)


def _require_sync_queue() -> None:
    """Refuse to run on any backend where composing workers is meaningless."""
    match get_settings().queue.queue_backend:
        case QueueBackendType.SYNC:
            return
        case backend:
            raise SystemExit(
                f"run_pipeline.py requires QUEUE_BACKEND=sync, found '{backend}'. "
                "On any other backend a subscriber blocks in start(), so the "
                "crawl step would never be reached — run each worker as its own "
                "process instead."
            )


def main() -> None:
    load_dotenv()
    args = _parse_args()

    # Before subscribing: worker-embed verifies the embedding dimension at
    # startup, which is a real billed call. Fail on misconfiguration first.
    _require_sync_queue()

    for subscribe in _SUBSCRIBING_WORKERS:
        subscribe()

    logger.info("All downstream handlers registered; starting crawl")
    run_crawl(["--years", args.years] if args.years else [])


if __name__ == "__main__":
    main()
