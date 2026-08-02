"""Unit tests for the embedding-model token ruler."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from ai.llm_config import EmbeddingBackend, EmbeddingConfig
from ai.tokenization import (
    EmbeddingRuler,
    _load_tokenizer,
    create_embedding_ruler,
)

WINDOW = 512
MODEL = "intfloat/multilingual-e5-large"


def _make_tokenizer(token_count: int = 3, window: int = WINDOW) -> MagicMock:
    tokenizer = MagicMock()
    tokenizer.encode = MagicMock(return_value=[0] * token_count)
    tokenizer.model_max_length = window
    return tokenizer


def _stub_transformers(tokenizer: MagicMock) -> tuple[ModuleType, MagicMock]:
    """A stand-in for the library, good enough for `_load_tokenizer`'s import.

    `_load_tokenizer` imports `transformers` inside its body, so a stub in
    `sys.modules` intercepts it. Naming the real module as a patch target would
    import it — and torch with it — into a suite that must stay fast and offline.
    """
    module = ModuleType("transformers")
    auto_tokenizer = MagicMock()
    auto_tokenizer.from_pretrained = MagicMock(return_value=tokenizer)
    setattr(module, "AutoTokenizer", auto_tokenizer)
    return module, auto_tokenizer


def _config(model: str = MODEL) -> EmbeddingConfig:
    return EmbeddingConfig(provider=EmbeddingBackend.LOCAL, model=model, dimension=1024)


def _make_ruler(tokenizer: MagicMock, config: EmbeddingConfig | None = None):
    stub, auto_tokenizer = _stub_transformers(tokenizer)
    _load_tokenizer.cache_clear()
    with patch.dict(sys.modules, {"transformers": stub}):
        ruler = create_embedding_ruler(config or _config())
    return ruler, auto_tokenizer


class TestWindowOverride:
    """The escape hatch for a process that cannot reach the tokenizer."""

    def _override_ruler(self, window: int = 384) -> EmbeddingRuler:
        config = EmbeddingConfig(
            provider=EmbeddingBackend.LOCAL,
            model=MODEL,
            dimension=1024,
            window_override=window,
        )
        _load_tokenizer.cache_clear()
        # No stub in sys.modules: if the override still reached for the
        # tokenizer, the import would be real and this test would pay for torch.
        return create_embedding_ruler(config)

    def test_no_tokenizer_is_loaded(self) -> None:
        # Patching the module global is what `create_embedding_ruler` actually
        # looks up; patching `_load_tokenizer.__wrapped__` would not, because the
        # lru_cache wrapper holds its own reference and the assertion would pass
        # whether or not a tokenizer was loaded.
        with patch("ai.tokenization._load_tokenizer") as load:
            self._override_ruler()

        load.assert_not_called()

    def test_window_is_the_overridden_value(self) -> None:
        assert self._override_ruler(window=384).max_sequence_tokens == 384

    def test_estimate_rounds_up(self) -> None:
        count = self._override_ruler().count_tokens

        assert count("") == 0
        assert count("abc") == 2  # 3 chars / 2.0, rounded up

    def test_estimate_never_undercounts_real_swedish_text(self) -> None:
        # The whole point of the fallback: it may make chunks smaller than they
        # needed to be, but it must not let one overrun the window. 0.5 tokens
        # per character is the densest text measured on real decisions.
        count = self._override_ruler().count_tokens
        text = "Överklagandenämnden avslog kyrkoherdens överklagande."
        densest_possible = len(text) * 0.5

        assert count(text) >= densest_possible


def test_tokenizer_is_loaded_for_the_configured_model() -> None:
    _, auto_tokenizer = _make_ruler(_make_tokenizer())

    auto_tokenizer.from_pretrained.assert_called_once_with(MODEL)


def test_counts_content_tokens_without_specials() -> None:
    tokenizer = _make_tokenizer(token_count=7)
    ruler, _ = _make_ruler(tokenizer)

    assert ruler.count_tokens("någon text") == 7
    # Every budget number is derived assuming specials are counted once for the
    # whole input, not once per piece.
    tokenizer.encode.assert_called_once_with("någon text", add_special_tokens=False)


def test_window_comes_from_the_tokenizer() -> None:
    ruler, _ = _make_ruler(_make_tokenizer(window=384))

    assert ruler.max_sequence_tokens == 384


def test_tokenizer_is_loaded_once_per_process() -> None:
    stub, auto_tokenizer = _stub_transformers(_make_tokenizer())
    _load_tokenizer.cache_clear()

    with patch.dict(sys.modules, {"transformers": stub}):
        create_embedding_ruler(_config())
        create_embedding_ruler(_config())

    # Both workers are composed into one process by scripts/run_pipeline.py.
    assert auto_tokenizer.from_pretrained.call_count == 1
