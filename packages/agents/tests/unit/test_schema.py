"""What the model is shown, and the policy sets derived from the same source.

These tests run against the *shipped* `semantic_model.yaml` rather than a
fixture, because the thing worth asserting is that the real prompt says what it
needs to say. Whether the loader rejects a broken file is
`test_semantic_model.py`'s job.
"""

from __future__ import annotations

import pytest

from agents.sql._schema import (
    blocked_columns,
    build_examples_block,
    build_schema_description,
    exposed_column_names,
    exposed_tables,
    grounding_required_columns,
)
from agents.sql._semantic_model import (
    SemanticModelDocument,
    find_semantic_model_path,
    load_semantic_model,
)


@pytest.fixture(scope="module")
def document() -> SemanticModelDocument:
    return load_semantic_model(find_semantic_model_path())


def test_non_corpus_tables_are_not_exposed(document: SemanticModelDocument) -> None:
    assert "sessions" not in exposed_tables(document)
    assert "tasks" not in exposed_tables(document)


def test_description_covers_every_exposed_table(
    document: SemanticModelDocument,
) -> None:
    description = build_schema_description(document)
    for table in exposed_tables(document):
        assert f"{table} —" in description


def test_blocked_columns_are_listed_but_marked(
    document: SemanticModelDocument,
) -> None:
    """Listed rather than hidden, so the model knows why it cannot have them.

    A column that simply vanished from the schema invites the model to guess at
    a name; one marked unusable does not.
    """
    description = build_schema_description(document)
    blocked = blocked_columns(document)
    assert blocked, "the shipped model should block the payload-sized columns"
    for column in blocked:
        assert column in description
    assert description.count("[EJ VALBAR]") == len(blocked)


def test_free_text_columns_are_flagged_as_such(
    document: SemanticModelDocument,
) -> None:
    """The single most important thing the prompt has to convey.

    The marker is rendered from the `free_text` flag rather than typed into the
    note, so this asserts the flag and the prose cannot disagree.
    """
    description = build_schema_description(document)
    required = grounding_required_columns(document)
    assert ("documents", "decision_outcome") in required
    assert ("documents", "category") in required

    for _table, column in required:
        note_line = next(
            line for line in description.splitlines() if line.strip().startswith(column)
        )
        assert "FRITEXT" in note_line

    assert description.count("FRITEXT") == len(required)


def test_a_note_never_hand_writes_a_marker(document: SemanticModelDocument) -> None:
    """Both markers are rendered from flags. Typing one into the prose is how the
    two come to disagree, so the file must not contain either."""
    for table in document.tables.values():
        for name, column in table.columns.items():
            assert "FRITEXT" not in column.note, name
            assert "EJ VALBAR" not in column.note, name


def test_exposed_columns_match_the_exposed_tables(
    document: SemanticModelDocument,
) -> None:
    assert {table for table, _ in exposed_column_names(document)} == exposed_tables(
        document
    )


def test_structural_facts_come_from_the_orm(document: SemanticModelDocument) -> None:
    """Types, nullability and foreign keys are never written in the YAML."""
    description = build_schema_description(document)
    assert "chunks.document_id" not in description  # not restated as prose
    assert "document_id (UUID, not null) -> documents.id" in description
    assert "embedding (VECTOR(1024), null)" in description


def test_examples_are_rendered_with_their_sql_and_reasoning(
    document: SemanticModelDocument,
) -> None:
    examples = build_examples_block(document)
    assert document.examples, "the shipped model should carry worked examples"
    for example in document.examples:
        assert example.sql.strip() in examples
    assert "Kommentar:" in examples


def test_notes_are_collapsed_onto_one_line(document: SemanticModelDocument) -> None:
    """YAML block scalars arrive with newlines; a column must stay one line, or
    the indentation stops distinguishing columns from tables."""
    description = build_schema_description(document)
    column_lines = [line for line in description.splitlines() if line.startswith("  ")]
    assert len(column_lines) == len(exposed_column_names(document))
