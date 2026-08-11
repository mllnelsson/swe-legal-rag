"""Run one AI task over a list of inputs and record every result.

`run_step.py` does this for the ingestion pipeline; this does it for the LLM side.
An input file holds one input per line, the inputs run in sequence, and each one's
input and output is appended to a JSONL file as it completes. Change a prompt, run
the same file again, and the two runs are directly comparable.

What a line *means* is the task's own business — a question for `sql`, a path to a
decision text file for `summarize` — so each task states it at registration and
``--help`` renders it.

Usage (run from repo root, .env configured):

    uv run python scripts/run_agent.py sql       questions.txt
    uv run python scripts/run_agent.py summarize decisions.txt
    uv run python scripts/run_agent.py sql       questions.txt --limit 3
    uv run python scripts/run_agent.py sql       questions.txt --out data/runs/before.jsonl

Blank lines and ``#`` comments in the input file are skipped, so a curated question
set can carry section headings.

A case that raises is recorded with its error and the run continues to the next
input — that is what makes this a batch runner rather than twenty invocations. The
file is flushed after every case, so a run killed part-way keeps what it had. The
exit code is 1 if any case failed.

Prompts and token counts are deliberately *not* duplicated into the records here.
Every case runs inside a ``trace_context`` carrying this run's ``run_id`` and the
case number, so the full prompt, the response and the usage for any line are one
grep away in the trace stream — see documentation/observability.md.

See documentation/playbooks/live-testing.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from ai import LLMRole, create_llm_provider, install_file_tracing, trace_context
from shared.db import get_async_session
from shared.logging_config import configure_logging

logger = logging.getLogger("run_agent")

# Attribution for traces from this script; the agents name themselves inside.
_SOURCE = "scripts.run_agent"

# Bumped only when a field changes meaning or disappears. Adding a field does not
# break a reader and does not bump this — same convention as the trace stream.
RESULT_SCHEMA_VERSION = 1

# `data/` is gitignored and is where `run_step.py --store fs` writes too.
DEFAULT_OUTPUT_DIR = Path("data/agent-runs")

_RUN_ID_FORMAT = "%Y%m%dT%H%M%SZ"
_COMMENT_PREFIX = "#"
_MILLISECONDS_PER_SECOND = 1000

# UTF-8 without escaping: every prompt in this project is Swedish, and
# \uXXXX-escaping them makes the output unreadable for no benefit.
_JSON_ENSURE_ASCII = False

# How much of an input to echo in the progress log. The whole thing is in the
# record; this line only has to be recognisable.
_LOG_INPUT_CHARS = 80


class AgentTask(StrEnum):
    SQL = "sql"
    SUMMARIZE = "summarize"


# One input in, the JSON-ready output out. Everything a task needs to build first
# — a provider, the semantic model, a tokenizer — is closed over by its preparer,
# so the per-case call carries no setup cost.
type TaskRunner = Callable[[str], Awaitable[dict[str, Any]]]
type TaskPreparer = Callable[[AsyncSession], Awaitable[TaskRunner]]


@dataclass(frozen=True)
class InputLine:
    """One input, and where in the file it came from.

    The line number is kept because comments and blank lines are skipped: case 7
    is rarely line 7, and a failure has to be traceable back to what you edit.
    """

    text: str
    source_line: int


@dataclass(frozen=True)
class TaskSpec:
    """One AI task this harness can run over a list of inputs."""

    prepare: TaskPreparer
    # What a line of the input file means for this task. Stated here rather than
    # in the parser so a new task cannot be registered without saying.
    input_help: str


async def _prepare_sql(session: AsyncSession) -> TaskRunner:
    """The text-to-SQL agent: a question in, a query and its rows out."""
    from agents import SqlAgentRequest, check_semantic_model, run_sql_agent

    # Before the first billed call rather than after twenty. This is the check the
    # API makes fatal at startup, and answers from an agent whose semantic model
    # has drifted from the ORM are not worth paying for.
    check_semantic_model()
    provider = create_llm_provider(LLMRole.SQL)

    async def run(question: str) -> dict[str, Any]:
        result = await run_sql_agent(
            SqlAgentRequest(question=question), session, llm_provider=provider
        )
        return result.model_dump()

    return run


async def _prepare_summarize(_session: AsyncSession) -> TaskRunner:
    """The chunk worker's summariser, over a decision read from a file.

    Takes no session — its input is a path — but keeps the preparer signature so
    the registry stays one shape.
    """
    from ai import create_embedding_ruler, summarize_document
    from shared.segmentation import split_document
    from worker_chunk.budget import SUMMARY_RESERVE_TOKENS

    provider = create_llm_provider(LLMRole.SUMMARIZE)
    # The same ruler worker-chunk measures with. Counting the summary in any other
    # tokenizer answers a different question than the one that decides truncation.
    ruler = create_embedding_ruler()

    async def run(path: str) -> dict[str, Any]:
        raw_text = Path(path).read_text(encoding="utf-8")
        # Body only, exactly as worker-chunk does: the pipeline never summarises
        # the appendices, so skipping this would measure a prompt input that
        # production never sends.
        body = split_document(raw_text).body
        result = await summarize_document(body, provider=provider)
        tokens = ruler.count_tokens(result.summary)
        return {
            "summary": result.summary,
            "summary_tokens": tokens,
            "reserve_tokens": SUMMARY_RESERVE_TOKENS,
            # False means worker-chunk would truncate this one — the signal to
            # watch when iterating on the summarisation prompt.
            "within_reserve": tokens <= SUMMARY_RESERVE_TOKENS,
            "input_chars": len(raw_text),
            "body_chars": len(body),
        }

    return run


TASKS: dict[AgentTask, TaskSpec] = {
    AgentTask.SQL: TaskSpec(
        prepare=_prepare_sql,
        input_help="one question per line",
    ),
    AgentTask.SUMMARIZE: TaskSpec(
        prepare=_prepare_summarize,
        input_help="one path to a decision text file per line",
    ),
}


def read_inputs(path: Path) -> list[InputLine]:
    """One input per line, minus the blanks and the `#` comments."""
    inputs: list[InputLine] = []
    for source_line, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        text = raw.strip()
        if text and not text.startswith(_COMMENT_PREFIX):
            inputs.append(InputLine(text=text, source_line=source_line))
    return inputs


def default_output_path(task: AgentTask, run_id: str) -> Path:
    return DEFAULT_OUTPUT_DIR / f"{task}-{run_id}.jsonl"


def _write_record(out: TextIO, record: dict[str, Any]) -> None:
    out.write(json.dumps(record, ensure_ascii=_JSON_ENSURE_ASCII) + "\n")
    # Per case, not per run: a run killed at case 15 keeps the first 14.
    out.flush()


def _shorten(text: str) -> str:
    if len(text) <= _LOG_INPUT_CHARS:
        return text
    return text[:_LOG_INPUT_CHARS] + "..."


async def run_cases(
    runner: TaskRunner,
    inputs: Sequence[InputLine],
    out: TextIO,
    *,
    run_id: str,
    task: AgentTask,
) -> int:
    """Run every input in order, writing one record each. Returns the failures.

    `ok` in a record means the call completed — **not** that the agent answered.
    `run_sql_agent` returns `answered=False` for a question it cannot answer and
    never raises, so a record can perfectly well be `ok` and unanswered, and a
    reader that conflates the two will mistake a refusal for a crash.
    """
    failed = 0

    for index, line in enumerate(inputs, start=1):
        logger.info("[%d/%d] %s", index, len(inputs), _shorten(line.text))
        started_at = datetime.now(UTC)
        started_perf = perf_counter()
        output: dict[str, Any] | None = None
        error: dict[str, str] | None = None

        # `run_id` and `case` land on every trace record this case produces, which
        # is the join from this file back to the full prompts. An agent that sets
        # its own `source` or `interaction_id` further in wins those keys; these
        # two are ours alone and survive.
        with trace_context(run_id=run_id, case=index, source=_SOURCE):
            try:
                output = await runner(line.text)
            except Exception as exc:
                # Recorded rather than raised: one unreadable file must not cost
                # the other nineteen calls. `Exception` and not `BaseException`,
                # so Ctrl-C still stops the run.
                logger.exception("Case %d failed", index)
                failed += 1
                error = {"type": type(exc).__name__, "message": str(exc)}

        _write_record(
            out,
            {
                "schema_version": RESULT_SCHEMA_VERSION,
                "run_id": run_id,
                "task": str(task),
                "index": index,
                "source_line": line.source_line,
                "input": line.text,
                "started_at": started_at.isoformat().replace("+00:00", "Z"),
                "latency_ms": int(
                    (perf_counter() - started_perf) * _MILLISECONDS_PER_SECOND
                ),
                "ok": error is None,
                "error": error,
                "output": output,
            },
        )

    return failed


async def _dispatch(args: argparse.Namespace, inputs: Sequence[InputLine]) -> int:
    load_dotenv()
    # The wiring invariant in documentation/observability.md: a process that makes
    # LLM calls installs tracing once, before the first one.
    install_file_tracing()

    task = AgentTask(args.task)
    run_id = datetime.now(UTC).strftime(_RUN_ID_FORMAT)
    out_path = Path(args.out) if args.out else default_output_path(task, run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # One session for the run. `summarize` never touches it; the connection is
    # lazy, so holding it costs a task that does not use it nothing.
    async with get_async_session() as session:
        runner = await TASKS[task].prepare(session)
        with out_path.open("w", encoding="utf-8") as out:
            failed = await run_cases(runner, inputs, out, run_id=run_id, task=task)

    logger.info(
        "%s: %d ok, %d failed -> %s",
        run_id,
        len(inputs) - failed,
        failed,
        out_path,
    )
    return 1 if failed else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an AI task over a list of inputs and record every result.",
    )
    sub = parser.add_subparsers(dest="task", required=True)
    for task, spec in TASKS.items():
        task_parser = sub.add_parser(str(task), help=spec.input_help)
        task_parser.add_argument("input_file", help=f"Input file: {spec.input_help}.")
        task_parser.add_argument(
            "--out",
            default=None,
            help=f"Output JSONL. Default: {DEFAULT_OUTPUT_DIR}/{task}-<run_id>.jsonl.",
        )
        task_parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Run only the first N inputs — a cheap smoke run before the rest.",
        )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = _parse_args()

    try:
        inputs = read_inputs(Path(args.input_file))
    except OSError as exc:
        # The one failure that is the caller's typo rather than a defect.
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    if args.limit is not None:
        inputs = inputs[: args.limit]
    if not inputs:
        print(f"FAIL no inputs in {args.input_file}", file=sys.stderr)
        return 1

    return asyncio.run(_dispatch(args, inputs))


if __name__ == "__main__":
    raise SystemExit(main())
