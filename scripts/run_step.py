"""Manual per-step ingestion runner for local hand-testing.

Runs a SINGLE pipeline step against ONE document without cascading to the next
step, so each stage (download, parse, metadata, ...) can be iterated in
isolation instead of running the whole crawl->...->embed chain end to end.

Why this exists: with ``QUEUE_BACKEND=sync`` the workers are wired to hand off
to each other in-process, and a standalone worker's ``subscriber.start()`` is a
no-op. This script bypasses the queue entirely — it calls each worker's service
function directly with a no-op publisher, so a step runs and then stops.

Two stores:
- ``--store db`` (default): the real Postgres + SQLAlchemy repositories.
- ``--store fs``: JSON files under ``--store-dir`` (default ``./data/store``) via
  the file-backed fakes in ``_fsstore.py`` — no database at all. Ideal for
  iterating on one step over one object, then running the whole chain once happy.

Usage (run from repo root, .env configured):

    uv run python scripts/run_step.py [--store fs] docs              # list documents + task state
    uv run python scripts/run_step.py [--store fs] seed input.json   # create a doc to start mid-pipeline
    uv run python scripts/run_step.py [--store fs] crawl             # discover docs, create download tasks
    uv run python scripts/run_step.py [--store fs] crawl --years all # backfill the full decision history
    uv run python scripts/run_step.py [--store fs] download <doc_id> # fetch + store the PDF
    uv run python scripts/run_step.py [--store fs] parse    <doc_id> # PDF -> documents.raw_text
    uv run python scripts/run_step.py [--store fs] metadata <doc_id> # raw_text -> structured fields
    uv run python scripts/run_step.py [--store fs] extract  <doc_id> # entities + references
    uv run python scripts/run_step.py [--store fs] chunk    <doc_id> # contextual chunks
    uv run python scripts/run_step.py [--store fs] embed    <doc_id> # chunk embeddings
    uv run python scripts/run_step.py [--store fs] chain <doc_id> [--until STEP]  # run steps in order

Re-running a step is safe: the current step's task is reset to ``pending`` and
the immediate downstream task row is cleared first (the services create the next
step's task in the same transaction, which would otherwise hit the
``uq_tasks_document_id_step`` unique constraint on a second run).

See documentation/design/LIVE_TESTING.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

import _fsrepos
from _fsstore import FsSession, FsStore
from dotenv import load_dotenv
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai import install_file_tracing, trace_context
from shared.config import Settings, get_settings
from shared.db import get_async_session
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.enums import PipelineStep, TaskStatus
from shared.models.document import Document
from shared.models.task import Task
from shared.queue.base import QueueMessage
from shared.repositories import (
    ChunkRepo,
    DocumentEntityRepo,
    DocumentReferenceRepo,
    DocumentRepo,
    EntityRepo,
    TaskRepo,
    UnresolvedReferenceRepo,
    chunk,
    document,
    document_entity,
    document_reference,
    entity,
    task,
    unresolved_reference,
)
from shared.storage import create_storage_backend

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("run_step")

# Attribution for traces from this script; inner calls name themselves.
_SOURCE = "scripts.run_step"

# Ingestion order. Value is the step each stage hands off to (None = terminal).
PIPELINE: dict[PipelineStep, PipelineStep | None] = {
    PipelineStep.DOWNLOAD: PipelineStep.PARSE,
    PipelineStep.PARSE: PipelineStep.METADATA,
    PipelineStep.METADATA: PipelineStep.EXTRACT,
    PipelineStep.EXTRACT: PipelineStep.CHUNK,
    PipelineStep.CHUNK: PipelineStep.EMBED,
    PipelineStep.EMBED: None,
}


class NoopPublisher:
    """QueuePublisher that records hand-offs instead of dispatching them, so a
    single step can run without the downstream worker being subscribed."""

    def publish(self, topic: str, message: QueueMessage) -> None:
        logger.info(
            "[no-op] would publish -> topic=%s document=%s task=%s",
            topic,
            message.document_id,
            message.task_id,
        )


def _next_topic(step: PipelineStep) -> PipelineStep:
    """Next step for a non-terminal step (used as the publish topic)."""
    next_step = PIPELINE[step]
    assert next_step is not None, f"{step!r} is terminal and has no next topic"
    return next_step


@dataclass
class Repos:
    """The repository namespaces services consume — real modules or file-backed doubles
    behind the same injection Protocols."""

    document: DocumentRepo
    task: TaskRepo
    chunk: ChunkRepo
    entity: EntityRepo
    doc_entity: DocumentEntityRepo
    ref: DocumentReferenceRepo
    unresolved: UnresolvedReferenceRepo


class DbCtx:
    """Backend bound to a real Postgres AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repos = Repos(
            document=document,
            task=task,
            chunk=chunk,
            entity=entity,
            doc_entity=document_entity,
            ref=document_reference,
            unresolved=unresolved_reference,
        )

    async def document_exists(self, document_id: UUID) -> bool:
        return await self.session.get(Document, document_id) is not None

    async def prepare_task(self, document_id: UUID, step: PipelineStep) -> UUID:
        next_step = PIPELINE[step]
        if next_step is not None:
            await self.session.execute(
                delete(Task).where(
                    Task.document_id == document_id, Task.step == next_step
                )
            )
        task = (
            await self.session.execute(
                select(Task).where(Task.document_id == document_id, Task.step == step)
            )
        ).scalar_one_or_none()
        if task is None:
            task = Task(document_id=document_id, step=step, status=TaskStatus.PENDING)
            self.session.add(task)
        else:
            task.status = TaskStatus.PENDING
            task.error_message = None
            task.started_at = None
            task.completed_at = None
        await self.session.flush()
        return task.id

    async def list_docs(self) -> list[tuple[str, str, bool, int, str]]:
        documents = (
            (await self.session.execute(select(Document).order_by(Document.created_at)))
            .scalars()
            .all()
        )
        out: list[tuple[str, str, bool, int, str]] = []
        for doc in documents:
            tasks = (
                (
                    await self.session.execute(
                        select(Task).where(Task.document_id == doc.id)
                    )
                )
                .scalars()
                .all()
            )
            steps = " ".join(
                f"{t.step}:{t.status}" for t in sorted(tasks, key=lambda t: t.step)
            )
            out.append(
                (
                    str(doc.id),
                    steps,
                    doc.gcs_uri is not None,
                    len(doc.raw_text or ""),
                    doc.source_url,
                )
            )
        return out


class FsCtx:
    """Backend bound to a JSON-on-filesystem store (no database)."""

    def __init__(self, store: FsStore) -> None:
        self.store = store
        self.session = cast(AsyncSession, FsSession(store))
        self.repos = Repos(
            document=_fsrepos.document,
            task=_fsrepos.task,
            chunk=_fsrepos.chunk,
            entity=_fsrepos.entity,
            doc_entity=_fsrepos.document_entity,
            ref=_fsrepos.document_reference,
            unresolved=_fsrepos.unresolved_reference,
        )

    async def document_exists(self, document_id: UUID) -> bool:
        return any(d.id == document_id for d in self.store.rows["documents"])

    async def prepare_task(self, document_id: UUID, step: PipelineStep) -> UUID:
        next_step = PIPELINE[step]
        if next_step is not None:
            await _fsrepos.task.delete_by_document_and_step(
                self.session, document_id, next_step
            )
        return await _fsrepos.task.reset_to_pending(self.session, document_id, step)

    async def list_docs(self) -> list[tuple[str, str, bool, int, str]]:
        out: list[tuple[str, str, bool, int, str]] = []
        for doc in self.store.rows["documents"]:
            tasks = [t for t in self.store.rows["tasks"] if t.document_id == doc.id]
            steps = " ".join(
                f"{t.step}:{t.status}" for t in sorted(tasks, key=lambda t: t.step)
            )
            out.append(
                (
                    str(doc.id),
                    steps,
                    doc.gcs_uri is not None,
                    len(doc.raw_text or ""),
                    doc.source_url,
                )
            )
        return out


Ctx = DbCtx | FsCtx


@asynccontextmanager
async def open_ctx(args: argparse.Namespace) -> AsyncIterator[Ctx]:
    if args.store == "fs":
        yield FsCtx(FsStore(Path(args.store_dir)))
    else:
        async with get_async_session() as session:
            yield DbCtx(session)


async def _run_step(
    ctx: Ctx, settings: Settings, step: PipelineStep, document_id: UUID
) -> str:
    if not await ctx.document_exists(document_id):
        raise SystemExit(
            f"Document {document_id} not found. Run `crawl` or `docs` first."
        )
    task_id = await ctx.prepare_task(document_id, step)

    publisher = NoopPublisher()
    repos = ctx.repos
    session = ctx.session

    # Mirrors the workers: every LLM/embedding call this script makes is
    # billed, so it is attributed to the document that caused it.
    with trace_context(
        document_id=str(document_id), task_id=str(task_id), source=_SOURCE
    ):
        match step:
            case PipelineStep.CRAWL:
                raise SystemExit("Use the `crawl` command to run the crawl step.")
            case PipelineStep.DOWNLOAD:
                from worker_download.config import get_download_settings
                from worker_download.service import process_download

                ds = get_download_settings()
                await process_download(
                    QueueMessage(task_id=task_id, document_id=document_id),
                    session=session,
                    document_repo=repos.document,
                    task_repo=repos.task,
                    storage=create_storage_backend(settings.storage),
                    queue_publisher=publisher,
                    timeout=ds.download_request_timeout,
                    max_retries=ds.download_max_retries,
                    rate_limit_delay=ds.download_rate_limit_delay,
                    next_topic=ds.download_next_topic,
                )
            case PipelineStep.PARSE:
                from worker_parse.parser import parse_pdf_with_pypdfium2
                from worker_parse.service import process_parse

                await process_parse(
                    document_id=document_id,
                    task_id=task_id,
                    storage=create_storage_backend(settings.storage),
                    document_repo=repos.document,
                    task_repo=repos.task,
                    queue_publisher=publisher,
                    parser=parse_pdf_with_pypdfium2,
                    session=session,
                    next_topic=_next_topic(PipelineStep.PARSE),
                )
            case PipelineStep.METADATA:
                from worker_metadata.__main__ import _no_llm_extractor
                from worker_metadata.patterns import extract_metadata_rule_based
                from worker_metadata.service import process_metadata

                await process_metadata(
                    document_id=document_id,
                    task_id=task_id,
                    document_repo=repos.document,
                    task_repo=repos.task,
                    queue_publisher=publisher,
                    rule_extractor=extract_metadata_rule_based,
                    llm_extractor=_no_llm_extractor,
                    session=session,
                    next_topic=_next_topic(PipelineStep.METADATA),
                )
            case PipelineStep.EXTRACT:
                from worker_extract.extractors.factory import (
                    create_extraction_strategy,
                )
                from worker_extract.services.extraction_service import (
                    process_extraction,
                )

                await process_extraction(
                    document_id=document_id,
                    task_id=task_id,
                    document_repo=repos.document,
                    task_repo=repos.task,
                    entity_repo=repos.entity,
                    doc_entity_repo=repos.doc_entity,
                    ref_repo=repos.ref,
                    unresolved_repo=repos.unresolved,
                    queue_publisher=publisher,
                    session=session,
                    strategy=create_extraction_strategy(),
                    next_topic=_next_topic(PipelineStep.EXTRACT),
                )
            case PipelineStep.CHUNK:
                from worker_chunk.service import process_chunking

                await process_chunking(
                    document_id=document_id,
                    task_id=task_id,
                    document_repo=repos.document,
                    chunk_repo=repos.chunk,
                    task_repo=repos.task,
                    queue_publisher=publisher,
                    session=session,
                    next_topic=_next_topic(PipelineStep.CHUNK),
                )
            case PipelineStep.EMBED:
                from ai import create_embedding_provider, get_embedding_prefixes
                from worker_embed.service import process_embedding

                _, passage_prefix = get_embedding_prefixes()
                await process_embedding(
                    document_id=document_id,
                    task_id=task_id,
                    chunk_repo=repos.chunk,
                    task_repo=repos.task,
                    embedding_provider=create_embedding_provider(),
                    session=session,
                    passage_prefix=passage_prefix,
                )

    final = await repos.task.get_by_id(session, task_id)
    status = final.status if final else "unknown"
    logger.info(
        "Step %r finished for document %s -> task status=%s", step, document_id, status
    )
    if final and final.status == TaskStatus.FAILED:
        logger.error("Error: %s", final.error_message)
    return status


async def _run_chain(
    ctx: Ctx, settings: Settings, document_id: UUID, until: PipelineStep | None
) -> None:
    steps = list(PIPELINE)
    if until is not None:
        steps = steps[: steps.index(until) + 1]
    for step in steps:
        status = await _run_step(ctx, settings, step, document_id)
        if status != TaskStatus.COMPLETED:
            logger.error("Chain stopped at %r (status=%s)", step, status)
            return
    logger.info("Chain complete for document %s through %r", document_id, steps[-1])


_DOC_UPDATE_FIELDS = set(DocumentUpdate.model_fields)


async def _seed(ctx: Ctx, json_path: str) -> None:
    """Create one document from a JSON file so a step can be run from a known
    starting point (e.g. seed ``raw_text`` then run ``extract``).

    The JSON is an object with any of: ``source_url`` and the updatable document
    fields (``raw_text``, ``case_number``, ``decision_date``, ``summary``, ...).
    Prints the new document UUID to feed into the step commands.
    """
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    source_url = data.pop("source_url", "seed://manual")
    updates = {k: v for k, v in data.items() if k in _DOC_UPDATE_FIELDS}
    ignored = set(data) - _DOC_UPDATE_FIELDS
    if ignored:
        logger.warning(
            "Ignoring non-document fields in seed JSON: %s", ", ".join(sorted(ignored))
        )

    doc = await ctx.repos.document.create(
        ctx.session, DocumentCreate(source_url=source_url)
    )
    if updates:
        await ctx.repos.document.update(ctx.session, doc.id, DocumentUpdate(**updates))
    await ctx.session.commit()
    logger.info(
        "Seeded document %s (set: %s)", doc.id, ", ".join(sorted(updates)) or "none"
    )
    print(doc.id)


async def _run_crawl(ctx: Ctx, year_spec: str | None = None) -> None:
    from datetime import date

    from worker_crawl import odata
    from worker_crawl.config import get_crawl_settings, to_odata_config
    from worker_crawl.service import process_crawl
    from worker_crawl.years import resolve_years

    cs = get_crawl_settings()
    result = await process_crawl(
        session=ctx.session,
        document_repo=ctx.repos.document,
        task_repo=ctx.repos.task,
        queue_publisher=NoopPublisher(),
        source=odata,
        odata_config=to_odata_config(cs),
        selection=resolve_years(year_spec or cs.crawl_years, date.today()),
        topic=cs.crawl_topic,
    )
    logger.info(
        "Crawl complete: years=%s tags=%d found=%d new=%d skipped=%d",
        ",".join(str(year) for year in result.years_crawled) or "none",
        result.tags_used,
        result.total_found,
        result.new_documents,
        result.skipped,
    )


async def _list_docs(ctx: Ctx) -> None:
    rows = await ctx.list_docs()
    if not rows:
        print("No documents. Run: crawl")
        return
    for doc_id, steps, has_pdf, raw_len, source_url in rows:
        pdf = "pdf" if has_pdf else "no-pdf"
        print(f"{doc_id}  [{pdf} raw:{raw_len}]  {steps or '(no tasks)'}")
        print(f"    {source_url}")


async def _dispatch(args: argparse.Namespace) -> None:
    load_dotenv()
    # Before anything constructs a provider: metadata, extract, chunk and embed
    # all make billed calls from this script, and the wiring invariant in
    # documentation/observability.md applies to it as much as to the workers.
    install_file_tracing()
    if args.store == "fs":
        # fs mode never connects to Postgres, but Settings still validates a
        # DATABASE_URL — supply a throwaway one so the playground needs no DB.
        os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost/unused")
    settings = get_settings()
    async with open_ctx(args) as ctx:
        if args.command == "docs":
            await _list_docs(ctx)
        elif args.command == "seed":
            await _seed(ctx, args.json_file)
        elif args.command == "crawl":
            await _run_crawl(ctx, args.years)
        elif args.command == "chain":
            until = PipelineStep(args.until) if args.until is not None else None
            await _run_chain(ctx, settings, UUID(args.document_id), until)
        else:
            await _run_step(
                ctx, settings, PipelineStep(args.command), UUID(args.document_id)
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one ingestion step in isolation.")
    parser.add_argument(
        "--store",
        choices=("db", "fs"),
        default="db",
        help="Persistence backend: 'db' (Postgres) or 'fs' (JSON files). Default: db.",
    )
    parser.add_argument(
        "--store-dir",
        default="./data/store",
        help="Directory for the 'fs' store JSON files. Default: ./data/store.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("docs", help="List documents and their per-step task status.")
    seed_parser = sub.add_parser(
        "seed", help="Create one document from a JSON file (to start mid-pipeline)."
    )
    seed_parser.add_argument(
        "json_file", help="Path to a JSON object of document fields."
    )
    crawl_parser = sub.add_parser(
        "crawl", help="Discover documents and create download tasks."
    )
    crawl_parser.add_argument(
        "--years",
        default=None,
        help=(
            "Decision years to crawl: 'current' (default), 'all', '2019', '2019-2021', "
            "or a comma-separated mix. Overrides CRAWL_YEARS."
        ),
    )
    chain_parser = sub.add_parser(
        "chain", help="Run all steps in order for one document."
    )
    chain_parser.add_argument("document_id", help="Target document UUID (see `docs`).")
    chain_parser.add_argument(
        "--until", choices=tuple(PIPELINE), default=None, help="Stop after this step."
    )
    for step in PIPELINE:
        step_parser = sub.add_parser(
            step, help=f"Run the {step} step for one document."
        )
        step_parser.add_argument(
            "document_id", help="Target document UUID (see `docs`)."
        )
    asyncio.run(_dispatch(parser.parse_args()))


if __name__ == "__main__":
    main()
