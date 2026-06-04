import pytest

from shared.storage.local import LocalStorageBackend


def test_store_retrieve_roundtrip(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("file.pdf", b"hello world")
    assert backend.retrieve("file.pdf") == b"hello world"


def test_exists_true_after_store(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("doc.txt", b"data")
    assert backend.exists("doc.txt")


def test_exists_false_after_delete(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("doc.txt", b"data")
    backend.delete("doc.txt")
    assert not backend.exists("doc.txt")


def test_retrieve_raises_file_not_found(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    with pytest.raises(FileNotFoundError):
        backend.retrieve("nonexistent.pdf")


def test_delete_missing_key_is_noop(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.delete("nonexistent.pdf")  # should not raise


def test_get_url_returns_path(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("file.pdf", b"data")
    url = backend.get_url("file.pdf")
    assert "file.pdf" in url


def test_nested_key_creates_directories(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("documents/abc-123/original.pdf", b"content")
    assert backend.exists("documents/abc-123/original.pdf")
    assert (tmp_path / "documents" / "abc-123").is_dir()
