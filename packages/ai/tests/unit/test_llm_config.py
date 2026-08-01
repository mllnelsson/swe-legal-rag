"""Unit tests for `llm_config.yaml` loading and resolution.

Every test builds its own document from a temp file rather than reading the
repo's real `llm_config.yaml`: what is under test is the resolution rules, and
binding them to the shipped model names would turn a routine model swap into a
test failure.

The environment is the one thing these tests cannot own, so anything touching
precedence goes through `monkeypatch.setenv`/`delenv`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from ai.errors import (
    LLMConfigInvalidError,
    LLMConfigNotFoundError,
    UnknownLLMRoleError,
)
from ai.llm_config import (
    CONFIG_FILENAME,
    CONFIG_PATH_ENV,
    EmbeddingBackend,
    ProviderKind,
    find_config_path,
    get_embedding_prefixes,
    load_config_document,
    resolve_embedding_config,
    resolve_role_config,
    role_model_env_var,
)

# Every environment variable that can mask a file value, so a developer's real
# .env cannot change what these tests observe.
_PRECEDENCE_ENV_VARS = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_TEMPERATURE",
    "LLM_MAX_TOKENS",
    "LLM_BASE_URL",
    "LLM_STREAM_USAGE",
    "LLM_API_KEY",
    "LLM_MODEL_STRUCTURED",
    "LLM_MODEL_CHAT",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION",
    "BERGET_API_KEY",
    "GEMINI_API_KEY",
    CONFIG_PATH_ENV,
)

_DOCUMENT: dict[str, Any] = {
    "version": 1,
    "providers": {
        "berget": {
            "kind": "openai_compatible",
            "base_url": "https://api.berget.example/v1",
            "api_key_env": "BERGET_API_KEY",
        },
        "gemini": {"kind": "gemini", "api_key_env": "GEMINI_API_KEY"},
    },
    "defaults": {
        "provider": "berget",
        "temperature": 0.0,
        "max_tokens": None,
        "stream_usage": True,
    },
    "roles": {
        "structured": {"model": "cheap-model"},
        "chat": {"model": "strong-model", "temperature": 0.7, "max_tokens": 2048},
        "elsewhere": {"provider": "gemini", "model": "gemini-model"},
    },
    "embedding": {
        "provider": "berget",
        "model": "embed-model",
        "dimension": 1024,
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
    },
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _PRECEDENCE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _write(tmp_path: Path, document: dict[str, Any] | None = None) -> Path:
    path = tmp_path / CONFIG_FILENAME
    path.write_text(yaml.safe_dump(document or _DOCUMENT), encoding="utf-8")
    return path


class TestInheritance:
    def test_role_without_provider_uses_defaults(self, tmp_path: Path) -> None:
        document = load_config_document(_write(tmp_path))

        config = resolve_role_config("structured", document)

        assert config.provider == ProviderKind.OPENAI_COMPATIBLE
        assert config.model == "cheap-model"
        assert config.base_url == "https://api.berget.example/v1"
        assert config.temperature == 0.0

    def test_role_overrides_beat_defaults(self, tmp_path: Path) -> None:
        document = load_config_document(_write(tmp_path))

        config = resolve_role_config("chat", document)

        assert config.temperature == 0.7
        assert config.max_tokens == 2048

    def test_role_can_choose_a_different_provider(self, tmp_path: Path) -> None:
        """The point of the whole file: two roles, two hosts, one process."""
        document = load_config_document(_write(tmp_path))

        structured = resolve_role_config("structured", document)
        elsewhere = resolve_role_config("elsewhere", document)

        assert structured.provider == ProviderKind.OPENAI_COMPATIBLE
        assert elsewhere.provider == ProviderKind.GEMINI
        # Gemini declares no base_url, so the client falls back to its own.
        assert elsewhere.base_url is None

    def test_api_key_comes_from_the_variable_the_provider_names(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BERGET_API_KEY", "berget-secret")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
        document = load_config_document(_write(tmp_path))

        assert resolve_role_config("structured", document).api_key == "berget-secret"
        assert resolve_role_config("elsewhere", document).api_key == "gemini-secret"


class TestEnvironmentPrecedence:
    def test_per_role_model_env_beats_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_CHAT", "override-model")
        document = load_config_document(_write(tmp_path))

        assert resolve_role_config("chat", document).model == "override-model"
        # ...and only that role.
        assert resolve_role_config("structured", document).model == "cheap-model"

    def test_global_llm_model_does_not_leak_into_roles(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_MODEL pre-dates roles and is process-wide.

        Letting it through would silently collapse every role onto one model,
        which is the opposite of what this file exists to express.
        """
        monkeypatch.setenv("LLM_MODEL", "one-model-to-rule-them-all")
        document = load_config_document(_write(tmp_path))

        assert resolve_role_config("chat", document).model == "strong-model"
        assert resolve_role_config("structured", document).model == "cheap-model"

    def test_llm_provider_env_beats_role_and_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        document = load_config_document(_write(tmp_path))

        assert resolve_role_config("structured", document).provider == "gemini"

    def test_temperature_env_beats_a_role_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_TEMPERATURE", "0.25")
        document = load_config_document(_write(tmp_path))

        assert resolve_role_config("chat", document).temperature == 0.25

    def test_role_provider_masked_by_env_is_logged(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Env winning is intended; doing it invisibly is not."""
        monkeypatch.setenv("LLM_PROVIDER", "berget")
        document = load_config_document(_write(tmp_path))

        with caplog.at_level("WARNING"):
            resolve_role_config("elsewhere", document)

        assert "LLM_PROVIDER" in caplog.text
        assert "elsewhere" in caplog.text

    def test_no_warning_when_env_agrees_with_the_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        document = load_config_document(_write(tmp_path))

        with caplog.at_level("WARNING"):
            resolve_role_config("elsewhere", document)

        assert caplog.text == ""


class TestValidation:
    def test_role_naming_an_undeclared_provider_is_rejected(
        self, tmp_path: Path
    ) -> None:
        document = {**_DOCUMENT, "roles": {"chat": {"provider": "nope", "model": "m"}}}

        with pytest.raises(LLMConfigInvalidError, match="nope"):
            load_config_document(_write(tmp_path, document))

    def test_defaults_naming_an_undeclared_provider_is_rejected(
        self, tmp_path: Path
    ) -> None:
        document = {**_DOCUMENT, "defaults": {"provider": "nope"}}

        with pytest.raises(LLMConfigInvalidError, match="nope"):
            load_config_document(_write(tmp_path, document))

    def test_embedding_provider_may_be_local(self, tmp_path: Path) -> None:
        document = {
            **_DOCUMENT,
            "embedding": {**_DOCUMENT["embedding"], "provider": "local"},
        }

        config = resolve_embedding_config(
            load_config_document(_write(tmp_path, document))
        )

        assert config.provider == EmbeddingBackend.LOCAL
        # No host means no key and no base URL to inherit.
        assert config.api_key is None
        assert config.base_url is None

    def test_embedding_provider_must_otherwise_be_declared(
        self, tmp_path: Path
    ) -> None:
        document = {
            **_DOCUMENT,
            "embedding": {**_DOCUMENT["embedding"], "provider": "nope"},
        }

        with pytest.raises(LLMConfigInvalidError, match="nope"):
            load_config_document(_write(tmp_path, document))

    def test_unknown_top_level_key_is_rejected(self, tmp_path: Path) -> None:
        """A typo that silently does nothing looks like a setting that took effect."""
        document = {**_DOCUMENT, "rolez": {}}

        with pytest.raises(LLMConfigInvalidError):
            load_config_document(_write(tmp_path, document))

    def test_unknown_role_key_is_rejected(self, tmp_path: Path) -> None:
        document = {
            **_DOCUMENT,
            "roles": {"chat": {"model": "m", "temperatur": 0.5}},
        }

        with pytest.raises(LLMConfigInvalidError):
            load_config_document(_write(tmp_path, document))

    def test_unsupported_version_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(LLMConfigInvalidError, match="version"):
            load_config_document(_write(tmp_path, {**_DOCUMENT, "version": 99}))

    def test_non_mapping_document_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / CONFIG_FILENAME
        path.write_text("- just\n- a list\n", encoding="utf-8")

        with pytest.raises(LLMConfigInvalidError, match="mapping"):
            load_config_document(path)


class TestDiscovery:
    def test_config_path_env_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write(tmp_path)
        monkeypatch.setenv(CONFIG_PATH_ENV, str(path))

        assert find_config_path() == path

    def test_config_path_env_pointing_nowhere_is_fatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(CONFIG_PATH_ENV, str(tmp_path / "absent.yaml"))

        with pytest.raises(LLMConfigNotFoundError, match=CONFIG_PATH_ENV):
            find_config_path()

    def test_found_by_walking_up_from_the_working_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pytest is routinely run from a package subdirectory in this workspace."""
        path = _write(tmp_path)
        nested = tmp_path / "packages" / "ai"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        assert find_config_path() == path

    def test_missing_file_names_where_it_looked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A silent fallback to built-in defaults is how config drifts unnoticed."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(LLMConfigNotFoundError) as excinfo:
            find_config_path()

        assert CONFIG_FILENAME in str(excinfo.value)
        assert CONFIG_PATH_ENV in str(excinfo.value)


class TestRoles:
    def test_unknown_role_lists_the_declared_ones(self, tmp_path: Path) -> None:
        document = load_config_document(_write(tmp_path))

        with pytest.raises(UnknownLLMRoleError) as excinfo:
            resolve_role_config("rerank", document)

        assert "rerank" in str(excinfo.value)
        assert "structured" in str(excinfo.value)

    def test_a_role_added_to_the_file_needs_no_code_change(
        self, tmp_path: Path
    ) -> None:
        document = {
            **_DOCUMENT,
            "roles": {**_DOCUMENT["roles"], "rerank": {"model": "rerank-model"}},
        }

        config = resolve_role_config(
            "rerank", load_config_document(_write(tmp_path, document))
        )

        assert config.model == "rerank-model"

    def test_role_model_env_var_name_is_derived_from_the_role(self) -> None:
        assert role_model_env_var("chat") == "LLM_MODEL_CHAT"
        assert role_model_env_var("re-rank") == "LLM_MODEL_RE_RANK"


class TestEmbedding:
    def test_hosted_embedding_inherits_its_provider_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BERGET_API_KEY", "berget-secret")
        document = load_config_document(_write(tmp_path))

        config = resolve_embedding_config(document)

        assert config.provider == EmbeddingBackend.OPENAI_COMPATIBLE
        assert config.model == "embed-model"
        assert config.dimension == 1024
        assert config.base_url == "https://api.berget.example/v1"
        assert config.api_key == "berget-secret"

    def test_embedding_env_beats_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EMBEDDING_MODEL", "other-model")
        monkeypatch.setenv("EMBEDDING_DIMENSION", "768")
        document = load_config_document(_write(tmp_path))

        config = resolve_embedding_config(document)

        assert config.model == "other-model"
        assert config.dimension == 768

    def test_both_prefixes_come_from_one_place(self, tmp_path: Path) -> None:
        """Prefixing one side of an asymmetric model is worse than prefixing neither."""
        document = load_config_document(_write(tmp_path))

        assert get_embedding_prefixes(document) == ("query: ", "passage: ")

    def test_prefixes_default_to_empty(self, tmp_path: Path) -> None:
        document = {
            **_DOCUMENT,
            "embedding": {
                "provider": "berget",
                "model": "embed-model",
                "dimension": 1024,
            },
        }

        assert get_embedding_prefixes(
            load_config_document(_write(tmp_path, document))
        ) == (
            "",
            "",
        )


class TestShippedConfig:
    def test_the_repo_config_loads_and_declares_the_roles_in_use(self) -> None:
        """The one test that reads the real file — it must at least be valid."""
        document = load_config_document(find_config_path())

        assert {"structured", "summarize", "chat"} <= set(document.roles)
