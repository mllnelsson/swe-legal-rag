"""The dev script is a thin shell around `agents.check_semantic_model`.

What it owns is the exit code and what lands on which stream, because that is
what a developer and a CI step actually consume. The checking itself is covered
in `packages/agents/tests/unit/test_semantic_model.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import check_semantic_model
from agents import SemanticModelIncompleteError

_GOOD = """\
version: 1
tables:
  entities:
    description: Entiteter.
    columns:
      id: Primärnyckel.
      name:
        note: Namnet i gemener.
        free_text: true
      type: Entitetstyp.
      created_at: När raden skapades.
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "semantic_model.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_matching_model_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SEMANTIC_MODEL_PATH", str(_write(tmp_path, _GOOD)))
    monkeypatch.setattr("sys.argv", ["check_semantic_model.py"])

    assert check_semantic_model.main() == 0
    assert "OK" in capsys.readouterr().out


def test_print_emits_the_rendered_prompt_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SEMANTIC_MODEL_PATH", str(_write(tmp_path, _GOOD)))
    monkeypatch.setattr("sys.argv", ["check_semantic_model.py", "--print"])

    assert check_semantic_model.main() == 0

    out = capsys.readouterr().out
    assert "Databasschema" in out
    # The point of --print: the flags are rendered as the model will read them.
    assert "FRITEXT" in out


def test_a_missing_description_exits_one_and_reports_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failure has to be loud on the stream a CI step reads."""
    broken = _GOOD.replace("      type: Entitetstyp.\n", "")
    monkeypatch.setenv("SEMANTIC_MODEL_PATH", str(_write(tmp_path, broken)))
    monkeypatch.setattr("sys.argv", ["check_semantic_model.py"])

    assert check_semantic_model.main() == 1

    captured = capsys.readouterr()
    assert "entities.type" in captured.err
    assert captured.out == ""


def test_an_unexpected_error_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only `AgentError` becomes an exit code; a real defect must still raise."""
    monkeypatch.setenv("SEMANTIC_MODEL_PATH", str(_write(tmp_path, _GOOD)))
    monkeypatch.setattr("sys.argv", ["check_semantic_model.py"])

    def explode(_document: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(check_semantic_model, "check_semantic_model", explode)

    with pytest.raises(RuntimeError):
        check_semantic_model.main()


def test_semantic_model_incomplete_is_an_agent_error() -> None:
    """`main` catches `AgentError`; the checker raises this. Keep them related."""
    assert issubclass(SemanticModelIncompleteError, check_semantic_model.AgentError)
