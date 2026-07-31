from unittest.mock import MagicMock, patch

import pytest

from shared.storage.gcs import GCSStorageBackend

BUCKET = "church-legal-db-test"


@pytest.fixture
def backend():
    """A GCSStorageBackend whose client and bucket are mocked.

    google-cloud-storage is an optional extra and is not installed in the unit
    test environment, so the module-level import guard is patched too.
    """
    with patch("shared.storage.gcs.gcs_storage") as gcs_storage:
        client = MagicMock()
        bucket = MagicMock()
        gcs_storage.Client.return_value = client
        client.bucket.return_value = bucket
        yield GCSStorageBackend(BUCKET)


def test_store_uploads_bytes_under_the_exact_key(backend):
    """The trace recorder writes whole batches through `store`."""
    key = "llm-traces/2026-07-30/20260730T101533123456Z-3f9a1c2d.jsonl"

    uri = backend.store(key, b'{"n":1}\n{"n":2}\n')

    backend._bucket.blob.assert_called_once_with(key)
    backend._bucket.blob.return_value.upload_from_string.assert_called_once_with(
        b'{"n":1}\n{"n":2}\n'
    )
    assert uri == f"gs://{BUCKET}/{key}"
