"""Unit tests for LocalEmbeddingProvider.

`_get_model` is the seam, not `sentence_transformers`. Naming the library as a
patch target would import it — `mock.patch` resolves its target eagerly — and
that pulls torch and transformers into a suite that is supposed to be fast and
offline. What is worth testing here is ours anyway: the empty-input shortcut, the
load-once guard, and the numpy-to-list conversion.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import numpy as np

from ai.embedding import EmbeddingConfig
from ai.providers.local_embeddings import LocalEmbeddingProvider

EMBEDDING_WIDTH = 768


def _make_provider() -> LocalEmbeddingProvider:
    config = EmbeddingConfig(
        EMBEDDING_MODEL="intfloat/multilingual-e5-large", EMBEDDING_PROVIDER="local"
    )
    return LocalEmbeddingProvider(config)


def _make_model(row_count: int) -> MagicMock:
    model = MagicMock()
    model.encode.return_value = np.zeros((row_count, EMBEDDING_WIDTH), dtype=np.float32)
    return model


async def test_embed_returns_one_plain_float_vector_per_text() -> None:
    provider = _make_provider()

    with patch.object(
        LocalEmbeddingProvider, "_get_model", return_value=_make_model(3)
    ):
        result = await provider.embed(["a", "b", "c"])

    assert len(result) == 3
    assert all(len(vector) == EMBEDDING_WIDTH for vector in result)
    # `encode` hands back a numpy array; callers are promised plain floats.
    assert isinstance(result[0][0], float)


def _stub_sentence_transformers(model: MagicMock) -> tuple[ModuleType, MagicMock]:
    """A stand-in for the library, good enough for `_get_model`'s import.

    `_get_model` imports `sentence_transformers` inside its body, so a stub in
    `sys.modules` intercepts it. Patching the name on our own module would not:
    it exists only under `TYPE_CHECKING`.
    """
    module = ModuleType("sentence_transformers")
    constructor = MagicMock(return_value=model)
    setattr(module, "SentenceTransformer", constructor)
    return module, constructor


async def test_model_is_loaded_once_and_reused() -> None:
    provider = _make_provider()
    assert provider._model is None

    model = _make_model(1)
    stub, constructor = _stub_sentence_transformers(model)
    with patch.dict(sys.modules, {"sentence_transformers": stub}):
        await provider.embed(["text"])
        await provider.embed(["text again"])

    assert constructor.call_count == 1
    assert provider._model is model


async def test_empty_input_never_loads_the_model() -> None:
    provider = _make_provider()

    with patch.object(LocalEmbeddingProvider, "_get_model") as get_model:
        result = await provider.embed([])

    assert result == []
    get_model.assert_not_called()
