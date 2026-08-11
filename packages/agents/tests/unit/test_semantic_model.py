"""The semantic model must describe the database that actually exists.

The agent is told what the corpus holds by two sources — SQLAlchemy metadata for
structure, `semantic_model.yaml` for meaning — and these tests are about what
happens when they disagree. That is not a theoretical failure: a column added by
a migration reaches the prompt as a bare name and type, and for a column like
`decision_outcome` the prose is exactly what stops it being misused.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.errors import (
    SemanticModelIncompleteError,
    SemanticModelInvalidError,
    SemanticModelNotFoundError,
)
from agents.sql._semantic_model import (
    CONFIG_PATH_ENV,
    SemanticModelDocument,
    check_semantic_model,
    find_semantic_model_path,
    load_semantic_model,
)

# `entities` is the smallest real table, so a document describing it exactly is
# short enough to read and still checks against live metadata.
_ENTITIES = """\
version: 1
tables:
  entities:
    description: Entiteter i besluten.
    columns:
      id: Primärnyckel.
      name:
        note: Entitetens namn i gemener.
        free_text: true
      type: Entitetstyp.
      created_at: När raden skapades.
"""


def _load(tmp_path: Path, body: str) -> SemanticModelDocument:
    path = tmp_path / "semantic_model.yaml"
    path.write_text(body, encoding="utf-8")
    return load_semantic_model(path)


def test_a_column_written_as_a_bare_string_is_a_note() -> None:
    """Most columns need only a sentence; spelling out `note:` for all of them
    would bury the handful that carry a flag."""
    document = SemanticModelDocument.model_validate(
        {
            "version": 1,
            "tables": {
                "entities": {"description": "E.", "columns": {"id": "Primärnyckel."}}
            },
        }
    )

    column = document.tables["entities"].columns["id"]
    assert column.note == "Primärnyckel."
    assert column.free_text is False
    assert column.selectable is True


def test_a_column_added_by_a_migration_fails_the_check(tmp_path: Path) -> None:
    """The reason this check exists at all."""
    document = _load(tmp_path, _ENTITIES.replace("      type: Entitetstyp.\n", ""))

    with pytest.raises(SemanticModelIncompleteError, match="entities.type"):
        check_semantic_model(document)


def test_a_description_left_behind_by_a_dropped_column_fails_too(
    tmp_path: Path,
) -> None:
    """Drift is checked in both directions — a stale note is a lie about the
    schema just as much as a missing one is a gap."""
    document = _load(tmp_path, _ENTITIES + "      slaktnamn: Finns inte.\n")

    with pytest.raises(SemanticModelIncompleteError, match="entities.slaktnamn"):
        check_semantic_model(document)


def test_every_disagreement_is_reported_at_once(tmp_path: Path) -> None:
    """A migration adding four columns should cost one round trip, not four."""
    document = _load(
        tmp_path,
        "version: 1\ntables:\n  entities:\n"
        "    description: E.\n    columns:\n      id: Primärnyckel.\n",
    )

    with pytest.raises(SemanticModelIncompleteError) as caught:
        check_semantic_model(document)

    message = str(caught.value)
    for column in ("entities.name", "entities.type", "entities.created_at"):
        assert column in message


def test_a_table_that_does_not_exist_is_named(tmp_path: Path) -> None:
    document = _load(
        tmp_path,
        "version: 1\ntables:\n  arkiv:\n"
        "    description: A.\n    columns:\n      id: Primärnyckel.\n",
    )

    with pytest.raises(SemanticModelIncompleteError, match="arkiv"):
        check_semantic_model(document)


@pytest.mark.parametrize("table", ["sessions", "tasks", "alembic_version"])
def test_non_corpus_tables_are_refused_outright(tmp_path: Path, table: str) -> None:
    """The floor.

    `sessions` holds user conversation history and `tasks` pipeline bookkeeping.
    Neither becomes corpus data because someone added it to a YAML, and the agent
    runs on the application's own connection — so this refusal and the allow-list
    derived from `tables:` are jointly what keeps them unreachable.
    """
    body = (
        f"version: 1\ntables:\n  {table}:\n"
        "    description: X.\n    columns:\n      id: Primärnyckel.\n"
    )

    with pytest.raises(SemanticModelInvalidError, match=table):
        _load(tmp_path, body)


def test_an_unsupported_version_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SemanticModelInvalidError, match="version"):
        _load(tmp_path, _ENTITIES.replace("version: 1", "version: 2"))


def test_an_unknown_key_is_refused(tmp_path: Path) -> None:
    """`extra="forbid"` throughout: a mistyped key that silently does nothing is
    worse than a startup failure, because it looks like the setting took effect."""
    with pytest.raises(SemanticModelInvalidError, match="freetext"):
        _load(
            tmp_path,
            _ENTITIES.replace("        free_text: true", "        freetext: true"),
        )


def test_malformed_yaml_is_reported_as_invalid(tmp_path: Path) -> None:
    with pytest.raises(SemanticModelInvalidError):
        _load(tmp_path, "version: 1\ntables: [this is not a mapping\n")


def test_a_top_level_list_is_reported_as_invalid(tmp_path: Path) -> None:
    with pytest.raises(SemanticModelInvalidError, match="mapping"):
        _load(tmp_path, "- version: 1\n")


def test_a_missing_file_names_the_variable_that_would_fix_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENV, str(tmp_path / "nowhere.yaml"))

    with pytest.raises(SemanticModelNotFoundError, match=CONFIG_PATH_ENV):
        find_semantic_model_path()


def test_the_shipped_model_is_found_and_valid() -> None:
    """The one that matters: what the API will actually load at startup."""
    check_semantic_model(load_semantic_model(find_semantic_model_path()))


# --- Examples ------------------------------------------------------------
#
# An example is a query the model is shown and invited to imitate, so one that
# the tools would refuse is worse than no example at all.


def _document_with_example(
    *, sql: str, grounding: list[tuple[str, str]] | None = None
) -> SemanticModelDocument:
    """A complete-but-tiny model, so these tests fail on the example and not on
    the completeness check that runs before it.

    `document_entities` is the corpus' smallest table. Flagging `relevance` as
    free text is a stretch of what that column really is, but the flag is the
    file's to declare and this is the shortest honest way to have one.
    """
    return SemanticModelDocument.model_validate(
        {
            "version": 1,
            "tables": {
                "document_entities": {
                    "description": "Kopplingstabell.",
                    "columns": {
                        "document_id": "Beslutet.",
                        "entity_id": "Entiteten.",
                        "relevance": {"note": "Hur central.", "free_text": True},
                    },
                }
            },
            "examples": [
                {
                    "question": "Fråga?",
                    "sql": sql,
                    "note": "Kommentar.",
                    "grounding": grounding or [],
                }
            ],
        }
    )


def test_an_example_the_guard_would_reject_fails_the_check() -> None:
    document = _document_with_example(sql="SELECT id, history FROM sessions")

    with pytest.raises(SemanticModelIncompleteError, match="guard"):
        check_semantic_model(document)


def test_an_example_that_skips_grounding_fails_the_check() -> None:
    """Examples are held to the same rule as the agent.

    Otherwise the prompt demonstrates a query `run_sql` refuses to run, and the
    model learns the rule is optional.
    """
    document = _document_with_example(
        sql="SELECT count(*) FROM document_entities WHERE relevance = 'primary'"
    )

    with pytest.raises(
        SemanticModelIncompleteError, match="document_entities.relevance"
    ):
        check_semantic_model(document)


def test_an_example_that_declares_its_grounding_passes() -> None:
    document = _document_with_example(
        sql="SELECT count(*) FROM document_entities WHERE relevance = 'primary'",
        grounding=[("document_entities", "relevance")],
    )

    check_semantic_model(document)


def test_an_example_that_only_groups_by_a_free_text_column_needs_no_grounding() -> None:
    """The agent's own act of grounding, shown as an example."""
    document = _document_with_example(
        sql="SELECT relevance, count(*) FROM document_entities GROUP BY 1"
    )

    check_semantic_model(document)
