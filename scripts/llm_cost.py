"""Price LLM traces at read time.

Trace records carry the served model and the provider's token counts but no
cost — cost is a pure function of those two, so it is applied here instead of
being frozen into the record. The practical consequence: adding a rate to
``ai/_pricing.py`` re-prices every trace ever written, rather than only the calls
that happen afterwards. That matters, because the Berget-hosted models this
project runs by default are currently unpriced.

Usage:

    uv run python scripts/llm_cost.py                      # today, by model
    uv run python scripts/llm_cost.py --date 2026-07-30
    uv run python scripts/llm_cost.py --interaction <uuid> # one chat question
    uv run python scripts/llm_cost.py --path some/dir      # any directory of .jsonl

Local storage only. On GCS the same summary comes from piping the objects in:
``gsutil cat 'gs://<bucket>/llm-traces/2026-07-30/*.jsonl' | uv run python
scripts/llm_cost.py --path -``.

This is a dev tool: it is intentionally outside the uv workspace packages and is
never imported by production code.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ai import estimate_cost_usd
from ai._observability import LLMTraceConfig
from llm_core import Usage
from shared.config import StorageSettings

TRACE_FILE_GLOB = "*.jsonl"

# Read stdin instead of a directory, so GCS objects can be piped in.
STDIN_PATH = "-"

_TABLE_WIDTH = 88
_MODEL_COLUMN = 44

UNPRICED = "unpriced"


@dataclass
class ModelTotals:
    model: str
    calls: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: Decimal | None = None
    # A model is unpriced as a whole; tracked separately from a zero cost.
    priced: bool = False


@dataclass
class Summary:
    records: int = 0
    by_model: dict[str, ModelTotals] = field(default_factory=dict)

    @property
    def total_cost(self) -> Decimal:
        return sum(
            (t.cost for t in self.by_model.values() if t.cost is not None),
            start=Decimal(0),
        )

    @property
    def unpriced_models(self) -> list[str]:
        return sorted(m for m, t in self.by_model.items() if not t.priced)


def _trace_directory(date: str) -> Path:
    settings = StorageSettings()
    config = LLMTraceConfig()
    return settings.local_storage_path / config.key_prefix / date


def _read_lines(path: Path | None) -> Iterator[str]:
    if path is None:
        yield from sys.stdin
        return
    for trace_file in sorted(path.glob(TRACE_FILE_GLOB)):
        yield from trace_file.read_text(encoding="utf-8").splitlines()


def load_records(path: Path | None) -> Iterator[dict[str, Any]]:
    """Yield every record, skipping blank and unparseable lines."""
    for number, line in enumerate(_read_lines(path), start=1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            print(f"warning: skipping unparseable line {number}", file=sys.stderr)


def _usage_of(record: dict[str, Any]) -> Usage | None:
    usage = record.get("usage")
    if usage is None:
        return None
    return Usage(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
    )


def summarize(records: Iterable[dict[str, Any]]) -> Summary:
    summary = Summary()
    for record in records:
        summary.records += 1
        model = record.get("model") or "(unreported)"
        totals = summary.by_model.setdefault(model, ModelTotals(model=model))

        totals.calls += 1
        if not record.get("success", True):
            totals.failures += 1

        usage = _usage_of(record)
        if usage is not None:
            totals.input_tokens += usage.input_tokens or 0
            totals.output_tokens += usage.output_tokens or 0

        cost = estimate_cost_usd(record.get("model"), usage)
        if cost is not None:
            totals.priced = True
            totals.cost = (totals.cost or Decimal(0)) + cost
    return summary


def _format_cost(totals: ModelTotals) -> str:
    if not totals.priced or totals.cost is None:
        return UNPRICED
    return f"{totals.cost:.8f}"


def print_summary(summary: Summary, source: str) -> None:
    print(f"\nLLM traces — {source}  ({summary.records} record(s))\n")
    header = (
        f"{'model':<{_MODEL_COLUMN}}{'calls':>7}{'in tok':>11}"
        f"{'out tok':>11}{'usd':>15}"
    )
    print(header)
    print("-" * _TABLE_WIDTH)

    for model in sorted(summary.by_model):
        totals = summary.by_model[model]
        label = model if len(model) <= _MODEL_COLUMN - 1 else model[: _MODEL_COLUMN - 2]
        print(
            f"{label:<{_MODEL_COLUMN}}{totals.calls:>7}"
            f"{totals.input_tokens:>11,}{totals.output_tokens:>11,}"
            f"{_format_cost(totals):>15}"
        )

    print("-" * _TABLE_WIDTH)
    calls = sum(t.calls for t in summary.by_model.values())
    input_tokens = sum(t.input_tokens for t in summary.by_model.values())
    output_tokens = sum(t.output_tokens for t in summary.by_model.values())
    print(
        f"{'TOTAL':<{_MODEL_COLUMN}}{calls:>7}{input_tokens:>11,}"
        f"{output_tokens:>11,}{summary.total_cost:>15.8f}"
    )

    failures = sum(t.failures for t in summary.by_model.values())
    if failures:
        print(f"\n{failures} failed call(s) included — a failed call is still billed.")

    unpriced = summary.unpriced_models
    if unpriced:
        print(
            f"\n{len(unpriced)} model(s) unpriced, so the total is a floor, not a "
            f"total:\n  " + "\n  ".join(unpriced)
        )
        print("Add a rate to ai/_pricing.py to price these retroactively.")


def _filter_interaction(
    records: Iterable[dict[str, Any]], interaction_id: str
) -> Iterator[dict[str, Any]]:
    for record in records:
        if record.get("context", {}).get("interaction_id") == interaction_id:
            yield record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--date",
        default=datetime.now(UTC).strftime("%Y-%m-%d"),
        help="UTC day to read (default: today).",
    )
    parser.add_argument(
        "--path",
        default=None,
        help=(
            f"Directory of {TRACE_FILE_GLOB} files, or {STDIN_PATH!r} for stdin. "
            "Overrides --date."
        ),
    )
    parser.add_argument(
        "--interaction",
        default=None,
        help="Only records for this interaction_id — the cost of one question.",
    )
    args = parser.parse_args()

    if args.path == STDIN_PATH:
        directory, source = None, "stdin"
    elif args.path is not None:
        directory, source = Path(args.path), args.path
    else:
        directory, source = _trace_directory(args.date), args.date
        if not directory.is_dir():
            print(f"No traces at {directory}", file=sys.stderr)
            raise SystemExit(1)

    records: Iterable[dict[str, Any]] = load_records(directory)
    if args.interaction:
        records = _filter_interaction(records, args.interaction)
        source = f"{source}, interaction {args.interaction}"

    print_summary(summarize(records), source)


if __name__ == "__main__":
    main()
