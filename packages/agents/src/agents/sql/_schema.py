"""Rendering the semantic model into the text the agent is given.

Loading and validating the model is `_semantic_model`'s job; this module only
turns a validated document plus live SQLAlchemy metadata into prompt text and
into the three policy sets the guard and the tools enforce.

The split matters: structural facts (type, nullability, foreign keys) are read
from `shared.models.Base.metadata` and so cannot drift, while meaning comes from
`semantic_model.yaml`. The `FRITEXT` and `[EJ VALBAR]` markers are rendered from
that file's flags rather than typed into its prose, so what the model reads and
what the code enforces are one fact, not two.

Every function takes an optional document and falls back to the process-wide
one, so a test can render an alternative model without touching the cache.
"""

from __future__ import annotations

from sqlalchemy import Table

from shared.models import Base

from agents.sql._semantic_model import SemanticModelDocument, resolve

__all__ = [
    "blocked_columns",
    "build_examples_block",
    "build_schema_description",
    "exposed_column_names",
    "exposed_tables",
    "grounding_required_columns",
]

_FREE_TEXT_MARKER = "FRITEXT"
_UNSELECTABLE_MARKER = "[EJ VALBAR]"


def exposed_tables(document: SemanticModelDocument | None = None) -> frozenset[str]:
    """The tables the agent may read.

    Everything else is unreachable by omission — including `sessions` and
    `tasks`, which the loader refuses outright.
    """
    return frozenset(resolve(document).tables)


def blocked_columns(document: SemanticModelDocument | None = None) -> frozenset[str]:
    """Column names that may never be selected, whatever table they sit on.

    Bare names rather than `(table, column)` pairs, matched table-agnostically:
    deliberately the more conservative reading, so `SELECT raw_text` is refused
    wherever it appears rather than only where the guard managed to work out
    which table it came from.
    """
    model = resolve(document)
    return frozenset(
        name
        for table in model.tables.values()
        for name, column in table.columns.items()
        if not column.selectable
    )


def grounding_required_columns(
    document: SemanticModelDocument | None = None,
) -> frozenset[tuple[str, str]]:
    """Free-text columns a predicate may not touch until their values are read."""
    model = resolve(document)
    return frozenset(
        (table_name, column_name)
        for table_name, table in model.tables.items()
        for column_name, column in table.columns.items()
        if column.free_text
    )


def exposed_column_names(
    document: SemanticModelDocument | None = None,
) -> set[tuple[str, str]]:
    """Every `(table, column)` the agent is allowed to know about."""
    model = resolve(document)
    return {
        (table_name, column_name)
        for table_name, table in model.tables.items()
        for column_name in table.columns
    }


def _orm_tables(document: SemanticModelDocument) -> list[Table]:
    """Exposed tables in metadata order, so the rendering is stable run to run."""
    exposed = set(document.tables)
    return [table for table in Base.metadata.sorted_tables if table.name in exposed]


def _foreign_key_note(table: Table, column_name: str) -> str:
    targets = sorted(
        fk.target_fullname for fk in table.columns[column_name].foreign_keys
    )
    return f" -> {', '.join(targets)}" if targets else ""


def _render_column(
    table: Table, column_name: str, document: SemanticModelDocument
) -> str:
    column = table.columns[column_name]
    spec = document.tables[table.name].columns[column_name]

    nullable = "null" if column.nullable else "not null"
    blocked = "" if spec.selectable else f" {_UNSELECTABLE_MARKER}"
    # Rendered from the flag, never from the note — that is what stops the prose
    # and the enforced policy from disagreeing.
    note = f"{_FREE_TEXT_MARKER} — {spec.note}" if spec.free_text else spec.note

    return (
        f"  {column_name} ({column.type}, {nullable})"
        f"{_foreign_key_note(table, column_name)}{blocked} — {_collapse(note)}"
    )


def _collapse(text: str) -> str:
    """One note, one line. YAML block scalars arrive with newlines in them."""
    return " ".join(text.split())


def build_schema_description(document: SemanticModelDocument | None = None) -> str:
    """The schema block handed to the model."""
    model = resolve(document)
    blocks: list[str] = []
    for table in _orm_tables(model):
        description = _collapse(model.tables[table.name].description)
        lines = [f"{table.name} — {description}"]
        lines.extend(
            _render_column(table, column.name, model) for column in table.columns
        )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_examples_block(document: SemanticModelDocument | None = None) -> str:
    """The worked queries handed to the model, in the order the file lists them."""
    model = resolve(document)
    blocks = [
        "\n".join(
            [
                f"Fråga: {_collapse(example.question)}",
                "SQL:",
                example.sql.strip(),
                f"Kommentar: {_collapse(example.note)}",
            ]
        )
        for example in model.examples
    ]
    return "\n\n".join(blocks)
