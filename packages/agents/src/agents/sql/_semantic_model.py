"""The semantic model document: loading `semantic_model.yaml` and proving it true.

The agent is told what the database holds by two sources that must agree. The
structural facts — types, nullability, foreign keys — come from
`shared.models.Base.metadata` and follow a migration automatically. Everything a
machine cannot derive — what a column means, which hold free-text prose, which
are too large to return, which tables exist at all — comes from this file.

`check_semantic_model()` is what keeps the two in step, and it checks both
directions: a described column that no longer exists is as wrong as an existing
column nobody described. It runs at API startup and is fatal there, because the
file supplies the table allow-list and the grounding policy rather than merely
prose — there is no reduced mode worth serving.

The loader mirrors `ai.llm_config`, which is this project's pattern for a
checked-in YAML document: `extra="forbid"` throughout, a walk-up path search, one
domain error per failure mode, and an `lru_cache`d getter.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Table

from shared.models import Base

from agents.errors import (
    SemanticModelIncompleteError,
    SemanticModelInvalidError,
    SemanticModelNotFoundError,
    SqlRejectedError,
)

__all__ = [
    "CONFIG_FILENAME",
    "CONFIG_PATH_ENV",
    "ColumnSpec",
    "ExampleSpec",
    "SemanticModelDocument",
    "TableSpec",
    "check_semantic_model",
    "find_semantic_model_path",
    "get_semantic_model",
    "load_semantic_model",
]

CONFIG_FILENAME = "semantic_model.yaml"
CONFIG_PATH_ENV = "SEMANTIC_MODEL_PATH"
SUPPORTED_VERSION = 1

# The floor. Enforced against the file rather than merely absent from it:
# `sessions` holds user conversation history and `tasks` pipeline bookkeeping,
# and neither becomes corpus data because someone added it to a YAML. The agent
# runs on the application's own connection, so this list and the table
# allow-list derived from `tables:` are jointly what keeps them unreachable.
_NEVER_EXPOSED = frozenset({"sessions", "tasks", "alembic_version"})


class ColumnSpec(BaseModel):
    """What one column means, and how the agent is allowed to treat it."""

    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1)
    # Prose rather than a categorical vocabulary. A predicate over such a column
    # must be grounded in the values that actually exist before it runs.
    free_text: bool = False
    # False for columns that exist but may never appear in a result: 1024 floats,
    # a lexeme index, a whole PDF's text.
    selectable: bool = True


class TableSpec(BaseModel):
    """One exposed table and every column on it."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    columns: dict[str, ColumnSpec]

    @field_validator("columns", mode="before")
    @classmethod
    def _allow_bare_note(cls, value: Any) -> Any:
        """Let a column with nothing to flag be written as a single string.

        Most columns need only a sentence; spelling out `note:` for all forty of
        them would bury the handful that carry a flag.
        """
        if not isinstance(value, dict):
            return value
        return {
            name: {"note": spec} if isinstance(spec, str) else spec
            for name, spec in value.items()
        }


class ExampleSpec(BaseModel):
    """A worked query shown to the agent.

    `grounding` names the free-text columns the query filters on, and is checked
    against the SQL rather than trusted: an example that skipped grounding would
    be teaching the model to write a query `run_sql` refuses to execute.
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    sql: str = Field(min_length=1)
    note: str = Field(min_length=1)
    grounding: list[tuple[str, str]] = Field(default_factory=list)


class SemanticModelDocument(BaseModel):
    """The whole of `semantic_model.yaml`, validated in isolation.

    Only self-consistency is checked here. Agreement with the ORM needs the
    metadata and lives in `check_semantic_model()`, so that a document can be
    constructed in a test without a database model in sight.
    """

    model_config = ConfigDict(extra="forbid")

    version: int
    tables: dict[str, TableSpec]
    examples: list[ExampleSpec] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: int) -> int:
        if value != SUPPORTED_VERSION:
            raise ValueError(
                f"Unsupported semantic model version {value}; "
                f"this build understands version {SUPPORTED_VERSION}"
            )
        return value

    @field_validator("tables")
    @classmethod
    def _check_never_exposed(cls, value: dict[str, TableSpec]) -> dict[str, TableSpec]:
        forbidden = sorted(set(value) & _NEVER_EXPOSED)
        if forbidden:
            raise ValueError(
                f"{', '.join(forbidden)} may never be exposed to the SQL agent: "
                "these hold conversation history and pipeline bookkeeping, not "
                "corpus data"
            )
        return value


def find_semantic_model_path() -> Path:
    """Locate `semantic_model.yaml`.

    `SEMANTIC_MODEL_PATH` wins if set. Otherwise walk up from the working
    directory: this is a uv workspace and pytest is routinely run from a package
    subdirectory, where the repo root is not the cwd.
    """
    override = os.environ.get(CONFIG_PATH_ENV)
    if override:
        path = Path(override)
        if not path.is_file():
            raise SemanticModelNotFoundError(
                f"{CONFIG_PATH_ENV} points at {path}, which does not exist"
            )
        return path

    start = Path.cwd().resolve()
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate

    raise SemanticModelNotFoundError(
        f"No {CONFIG_FILENAME} found in {start} or any parent directory. "
        f"Set {CONFIG_PATH_ENV} to point at it explicitly."
    )


def load_semantic_model(path: Path | None = None) -> SemanticModelDocument:
    """Read and validate the file. Prefer `get_semantic_model()` in callers."""
    path = path or find_semantic_model_path()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SemanticModelInvalidError(f"Could not read {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise SemanticModelInvalidError(
            f"{path} must contain a YAML mapping at the top level, "
            f"got {type(raw).__name__}"
        )

    try:
        return SemanticModelDocument.model_validate(raw)
    except ValueError as exc:
        raise SemanticModelInvalidError(f"{path} is invalid: {exc}") from exc


@lru_cache(maxsize=1)
def get_semantic_model() -> SemanticModelDocument:
    """The process-wide semantic model, read once."""
    return load_semantic_model()


def resolve(document: SemanticModelDocument | None) -> SemanticModelDocument:
    """The caller's document, or the process-wide one.

    Every reader of the semantic model takes an optional document so that tests
    can pass one without touching the cache — the same shape as
    `ai.llm_config.resolve_role_config`.
    """
    return document if document is not None else get_semantic_model()


def _orm_tables() -> dict[str, Table]:
    return {table.name: table for table in Base.metadata.sorted_tables}


def check_semantic_model(document: SemanticModelDocument | None = None) -> None:
    """Raise unless the semantic model and the ORM describe the same database.

    Deliberately reports every disagreement it finds rather than the first: a
    migration adding four columns should cost one round trip, not four.
    """
    document = resolve(document)
    orm_tables = _orm_tables()

    problems: list[str] = []
    for table_name, spec in document.tables.items():
        table = orm_tables.get(table_name)
        if table is None:
            problems.append(
                f"table {table_name!r} is described but does not exist "
                f"(known: {', '.join(sorted(orm_tables))})"
            )
            continue

        actual = {column.name for column in table.columns}
        described = set(spec.columns)
        for column in sorted(actual - described):
            problems.append(f"{table_name}.{column} exists but has no description")
        for column in sorted(described - actual):
            problems.append(f"{table_name}.{column} is described but does not exist")

    if problems:
        # Named generically rather than as CONFIG_FILENAME: SEMANTIC_MODEL_PATH
        # may point at another file, and a message naming the wrong one sends the
        # reader to edit a file that is fine.
        raise SemanticModelIncompleteError(
            "The semantic model and the ORM disagree:\n  " + "\n  ".join(problems)
        )

    _check_examples(document)


def _check_examples(document: SemanticModelDocument) -> None:
    """Hold every example to the rules the agent itself is held to.

    Imported here rather than at module scope because `_guard` reads its policy
    out of a document, which this module produces — importing it at the top
    would be a cycle.
    """
    from agents.sql._guard import check_sql, find_predicate_columns

    problems: list[str] = []
    for index, example in enumerate(document.examples):
        label = f"examples[{index}] ({example.question!r})"
        try:
            check_sql(example.sql, document)
        except SqlRejectedError as exc:
            problems.append(f"{label} is rejected by the SQL guard: {exc}")
            continue

        ungrounded = find_predicate_columns(example.sql, document) - set(
            example.grounding
        )
        if ungrounded:
            named = ", ".join(
                f"{table}.{column}" for table, column in sorted(ungrounded)
            )
            problems.append(
                f"{label} filters on {named} without declaring it under "
                "`grounding` — run_sql would refuse this query"
            )

    if problems:
        raise SemanticModelIncompleteError(
            "The semantic model contains examples the agent could not run:\n  "
            + "\n  ".join(problems)
        )
