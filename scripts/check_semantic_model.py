"""Check `semantic_model.yaml` against the ORM, and show what the SQL agent reads.

The same check the API runs at startup, available before you get that far. Run it
after any migration: a column added without a description, or a description left
behind by a dropped column, is a startup failure, and finding that here costs a
second rather than a deploy.

    uv run python scripts/check_semantic_model.py           # exit 0, or 1 with the reason
    uv run python scripts/check_semantic_model.py --print   # also dump the rendered prompt blocks

`--print` emits the exact schema and example text the model is given. That is the
only way to read it without making a billed call and going looking for the trace
record afterwards, so it is the tool to reach for when iterating on the prose.

See documentation/reference/semantic-model.md.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from agents import (
    AgentError,
    build_examples_block,
    build_schema_description,
    check_semantic_model,
    find_semantic_model_path,
    load_semantic_model,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate semantic_model.yaml against the ORM.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_prompt",
        help="print the rendered schema and examples the agent is given",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = _parse_args()

    try:
        path = find_semantic_model_path()
        # Loaded from the path rather than through the cached getter, so that
        # running this twice in one process still reads the file from disk.
        document = load_semantic_model(path)
        check_semantic_model(document)
    except AgentError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    tables = len(document.tables)
    columns = sum(len(table.columns) for table in document.tables.values())
    print(
        f"OK   {path}: {tables} tables, {columns} columns, "
        f"{len(document.examples)} examples — all match the ORM"
    )

    if args.print_prompt:
        print("\n--- Databasschema ---\n")
        print(build_schema_description(document))
        print("\n--- Exempel ---\n")
        print(build_examples_block(document))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
