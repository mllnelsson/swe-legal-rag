"""`LocalStorageBackend` is a thin pathlib wrapper, so only its decisions are
tested here — the explicit not-found error, the delete-is-idempotent contract,
and creating parent directories for a nested key. That `write_bytes` followed by
`read_bytes` returns what you wrote is pathlib's promise, not ours.
"""

import pytest

from shared.storage.local import LocalStorageBackend


def test_retrieve_raises_file_not_found(tmp_path):
    backend = LocalStorageBackend(tmp_path)

    with pytest.raises(FileNotFoundError):
        backend.retrieve("nonexistent.pdf")


def test_delete_missing_key_is_noop(tmp_path):
    """Deleting is idempotent: a redelivered message must not fail on cleanup."""
    backend = LocalStorageBackend(tmp_path)

    backend.delete("nonexistent.pdf")


def test_nested_key_creates_directories(tmp_path):
    backend = LocalStorageBackend(tmp_path)

    backend.store("documents/abc-123/original.pdf", b"content")

    assert backend.exists("documents/abc-123/original.pdf")
    assert (tmp_path / "documents" / "abc-123").is_dir()
