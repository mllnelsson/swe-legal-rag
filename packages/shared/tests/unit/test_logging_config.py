"""`LOG_LEVEL` resolution, including the `.env` path that is easy to lose."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from shared import logging_config
from shared.logging_config import configure_logging, resolve_log_level


@pytest.fixture(autouse=True)
def _restore_root_logger() -> Iterator[None]:
    """`configure_logging` passes ``force=True``, which is process-global."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore the developer's real `.env`, which may set LOG_LEVEL."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setattr(logging_config, "find_dotenv", lambda usecwd=True: "")


def test_defaults_to_info() -> None:
    assert resolve_log_level() == logging.INFO


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("debug", logging.DEBUG),
        ("DEBUG", logging.DEBUG),
        ("  WaRnInG ", logging.WARNING),
        ("error", logging.ERROR),
    ],
)
def test_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
) -> None:
    monkeypatch.setenv("LOG_LEVEL", raw)
    assert resolve_log_level() == expected


def test_rejects_a_value_that_is_not_a_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loudly, at startup — a silently ignored level is what this module is for."""
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        resolve_log_level()


def test_reads_dotenv_when_the_environment_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression test for the ordering trap.

    Every entry point calls `configure_logging()` *before* `load_dotenv()`, and in
    most workers `load_dotenv()` is not even in `main()`. Reading `os.environ`
    alone would make a `.env` LOG_LEVEL work under Docker (which injects it into
    the real environment) and silently do nothing under `uv run`.
    """
    monkeypatch.setattr(logging_config, "find_dotenv", lambda usecwd=True: "/tmp/.env")
    monkeypatch.setattr(
        logging_config, "dotenv_values", lambda path: {"LOG_LEVEL": "debug"}
    )
    assert resolve_log_level() == logging.DEBUG


def test_the_environment_beats_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "error")
    monkeypatch.setattr(logging_config, "find_dotenv", lambda usecwd=True: "/tmp/.env")
    monkeypatch.setattr(
        logging_config, "dotenv_values", lambda path: {"LOG_LEVEL": "debug"}
    )
    assert resolve_log_level() == logging.ERROR


def test_an_explicit_level_beats_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    configure_logging(logging.WARNING)
    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_applies_the_resolved_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    configure_logging()
    assert logging.getLogger().level == logging.DEBUG
