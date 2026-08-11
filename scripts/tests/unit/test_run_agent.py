"""The batch runner's own responsibilities, not the agents'.

What this script owns is the loop: that one bad input does not cost the rest of
the run, that a result is on disk the moment it exists rather than at the end,
that a refusal is not mistaken for a crash, and that each case is tied back to the
traces it produced. The agents themselves are covered under `packages/*/tests`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from llm_core import current_trace_context
from sqlalchemy.ext.asyncio import AsyncSession

import run_agent
from run_agent import AgentTask, InputLine, read_inputs, run_cases

_RUN_ID = "20260809T120000Z"


def _inputs(*texts: str) -> list[InputLine]:
    return [
        InputLine(text=text, source_line=index) for index, text in enumerate(texts, 1)
    ]


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def _run(
    tmp_path: Path, runner: Any, inputs: Sequence[InputLine]
) -> tuple[int, list[dict[str, Any]]]:
    out_path = tmp_path / "run.jsonl"
    with out_path.open("w", encoding="utf-8") as out:
        failed = await run_cases(
            runner, inputs, out, run_id=_RUN_ID, task=AgentTask.SQL
        )
    return failed, _records(out_path)


# --- The input file ------------------------------------------------------


def test_comments_and_blanks_are_skipped_but_line_numbers_are_kept(
    tmp_path: Path,
) -> None:
    """Case 7 is rarely line 7, and a failure has to point at what you edit."""
    path = tmp_path / "questions.txt"
    path.write_text(
        "# Utlämnande\nHur många avslogs 2026?\n\n  \n# Behörighet\nVilka nämnder?\n",
        encoding="utf-8",
    )

    assert read_inputs(path) == [
        InputLine(text="Hur många avslogs 2026?", source_line=2),
        InputLine(text="Vilka nämnder?", source_line=6),
    ]


# --- The loop ------------------------------------------------------------


async def test_a_failing_case_is_recorded_and_the_run_continues(
    tmp_path: Path,
) -> None:
    """The whole reason this is a batch runner: one bad input costs one input."""

    async def runner(text: str) -> dict[str, Any]:
        if text == "trasig":
            raise ValueError("no such file")
        return {"answer": text}

    failed, records = await _run(tmp_path, runner, _inputs("ett", "trasig", "tre"))

    assert failed == 1
    assert [record["ok"] for record in records] == [True, False, True]
    assert records[1]["error"] == {"type": "ValueError", "message": "no such file"}
    assert records[1]["output"] is None
    assert records[2]["output"] == {"answer": "tre"}


async def test_each_result_is_on_disk_before_the_next_case_starts(
    tmp_path: Path,
) -> None:
    """Flushing per case is what a run killed at 15 keeps 14 results by."""
    out_path = tmp_path / "run.jsonl"
    seen_during_case_two: list[dict[str, Any]] = []

    async def runner(text: str) -> dict[str, Any]:
        if text == "två":
            seen_during_case_two.extend(_records(out_path))
        return {"answer": text}

    with out_path.open("w", encoding="utf-8") as out:
        await run_cases(
            runner, _inputs("ett", "två"), out, run_id=_RUN_ID, task=AgentTask.SQL
        )

    assert [record["input"] for record in seen_during_case_two] == ["ett"]


async def test_an_unanswered_result_is_still_a_completed_call(tmp_path: Path) -> None:
    """`ok` means the call returned, not that the agent answered.

    `run_sql_agent` never raises for a question it cannot answer — it returns
    `answered=False`. A reader that conflates the two reads a refusal as a crash.
    """

    async def runner(_text: str) -> dict[str, Any]:
        return {"answered": False, "sql": None, "note": "Går inte att besvara."}

    failed, records = await _run(tmp_path, runner, _inputs("Vad tycker nämnden?"))

    assert failed == 0
    assert records[0]["ok"] is True
    assert records[0]["output"]["answered"] is False


async def test_every_case_runs_inside_its_own_trace_context(tmp_path: Path) -> None:
    """The join from a record back to the prompts that produced it.

    Nothing else ties a line of this file to the trace stream, which is why the
    prompts are not copied into the record.
    """

    async def runner(_text: str) -> dict[str, Any]:
        return dict(current_trace_context())

    _failed, records = await _run(tmp_path, runner, _inputs("ett", "två"))

    assert [record["output"]["case"] for record in records] == [1, 2]
    assert {record["output"]["run_id"] for record in records} == {_RUN_ID}


async def test_a_record_carries_the_run_and_the_source_line(tmp_path: Path) -> None:
    """A line is self-describing: there is no separate manifest to read."""

    async def runner(text: str) -> dict[str, Any]:
        return {"answer": text}

    _failed, records = await _run(
        tmp_path, runner, [InputLine(text="Hur många?", source_line=4)]
    )

    record = records[0]
    assert record["run_id"] == _RUN_ID
    assert record["task"] == "sql"
    assert record["index"] == 1
    assert record["source_line"] == 4
    assert record["input"] == "Hur många?"
    assert record["schema_version"] == run_agent.RESULT_SCHEMA_VERSION


# --- The summarize task --------------------------------------------------

_DECISION = """\
Överklagandenämndens beslut: Överklagandet avslås.

BILAGA A
Det överklagade beslutet i sin helhet.
"""


async def test_summarize_measures_the_body_and_not_the_appendices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pipeline summarises `split_document(...).body`.

    A harness that fed the whole file would be iterating on a prompt input
    production never sends — and would quietly summarise the decision that was
    appealed rather than the nämnd's own.
    """
    from ai import EmbeddingRuler, SummarizeResult

    async def fake_summarize(text: str, *, provider: object = None) -> SummarizeResult:
        return SummarizeResult(summary=text[:20])

    monkeypatch.setattr(run_agent, "create_llm_provider", lambda _role: None)
    monkeypatch.setattr(
        "ai.create_embedding_ruler",
        lambda: EmbeddingRuler(
            count_tokens=lambda text: len(text.split()), max_sequence_tokens=512
        ),
    )
    monkeypatch.setattr("ai.summarize_document", fake_summarize)

    path = tmp_path / "decision.txt"
    path.write_text(_DECISION, encoding="utf-8")

    # The summarize task never touches the session; it takes one only so every
    # preparer has the same signature.
    runner = await run_agent._prepare_summarize(cast("AsyncSession", object()))
    output = await runner(str(path))

    assert output["input_chars"] == len(_DECISION)
    assert output["body_chars"] < output["input_chars"]
    assert "BILAGA" not in output["summary"]
    assert output["reserve_tokens"] > 0
    assert output["within_reserve"] is True


# --- The command line ----------------------------------------------------


def test_a_missing_input_file_exits_one_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["run_agent.py", "sql", str(tmp_path / "gone.txt")])

    assert run_agent.main() == 1
    assert "gone.txt" in capsys.readouterr().err


def test_an_input_file_with_nothing_but_comments_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cheaper to say so than to open a database and build a provider first."""
    path = tmp_path / "questions.txt"
    path.write_text("# inget här\n\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["run_agent.py", "sql", str(path)])

    assert run_agent.main() == 1
    assert "no inputs" in capsys.readouterr().err


def test_every_task_states_what_a_line_means() -> None:
    """The registry is the one place a new task is registered; `--help` reads it."""
    for task in AgentTask:
        assert run_agent.TASKS[task].input_help
