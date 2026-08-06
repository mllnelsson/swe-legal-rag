import argparse
import asyncio
import logging
import sys
from datetime import date

from dotenv import load_dotenv

from shared.config import get_settings
from shared.db import dispose_async_engine, get_async_session
from shared.logging_config import configure_logging
from shared.queue import create_queue_publisher
from shared.repositories import document, task
from worker_crawl import odata
from worker_crawl.config import get_crawl_settings, to_odata_config
from worker_crawl.errors import CrawlError
from worker_crawl.service import process_crawl
from worker_crawl.years import resolve_years

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="worker_crawl",
        description="Crawl Överklagandenämnden decisions from the Svenska kyrkan API.",
    )
    parser.add_argument(
        "--years",
        default=None,
        help=(
            "Which decision years to crawl: 'current' (default), 'all', '2019', "
            "'2019-2021', or a comma-separated mix. Overrides CRAWL_YEARS. "
            "'all' additionally includes the year-less decision tag."
        ),
    )
    return parser.parse_args(argv)


async def _run(year_spec: str) -> None:
    settings = get_settings()
    crawl_settings = get_crawl_settings()

    selection = resolve_years(year_spec, date.today())
    publisher = create_queue_publisher(settings.queue)

    async with get_async_session() as session:
        result = await process_crawl(
            session=session,
            document_repo=document,
            task_repo=task,
            queue_publisher=publisher,
            source=odata,
            odata_config=to_odata_config(crawl_settings),
            selection=selection,
            topic=crawl_settings.crawl_topic,
        )

    # Downstream steps run after this loop closes, each in its own — so this
    # loop's connections must not be left in a pool for them to pick up.
    await dispose_async_engine()

    logger.info(
        "Crawl complete: years=%s tags=%d found=%d new=%d skipped=%d",
        ",".join(str(year) for year in result.years_crawled) or "none",
        result.tags_used,
        result.total_found,
        result.new_documents,
        result.skipped,
    )


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    load_dotenv()
    args = _parse_args(argv)
    year_spec = args.years or get_crawl_settings().crawl_years
    try:
        asyncio.run(_run(year_spec))
    except CrawlError as error:
        # Crawl failures are configuration or upstream-API problems, not bugs: report
        # them as a clean non-zero exit rather than a traceback.
        logger.error("%s", error)
        sys.exit(1)


if __name__ == "__main__":
    main()
