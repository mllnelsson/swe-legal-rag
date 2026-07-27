import json
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


def _uploaded_keys(backend):
    return [call.args[0] for call in backend._bucket.blob.call_args_list]


def test_add_json_writes_under_the_stream_key(backend):
    uri = backend.add_json("llm-traces/2026-07-27", {"operation": "generate"})

    key = _uploaded_keys(backend)[0]
    assert key.startswith("llm-traces/2026-07-27/")
    assert key.endswith(".json")
    assert uri == f"gs://{BUCKET}/{key}"


def test_add_json_mints_a_distinct_object_per_record(backend):
    backend.add_json("llm-traces/2026-07-27", {"n": 1})
    backend.add_json("llm-traces/2026-07-27", {"n": 2})

    keys = _uploaded_keys(backend)
    assert len(keys) == 2
    assert keys[0] != keys[1]


def test_add_json_uploads_json_content_type(backend):
    backend.add_json("llm-traces/2026-07-27", {"content": "Växjö"})

    blob = backend._bucket.blob.return_value
    data, kwargs = blob.upload_from_string.call_args
    assert kwargs["content_type"] == "application/json"
    assert json.loads(data[0])["content"] == "Växjö"


def test_iter_json_reads_blobs_in_key_order(backend):
    def _blob(name, payload):
        blob = MagicMock()
        blob.name = name
        blob.download_as_bytes.return_value = json.dumps(payload).encode("utf-8")
        return blob

    backend._client.list_blobs.return_value = [
        _blob("llm-traces/2026-07-27/20260727T000002Z-bbbb.json", {"n": 2}),
        _blob("llm-traces/2026-07-27/20260727T000001Z-aaaa.json", {"n": 1}),
    ]

    assert [record["n"] for record in backend.iter_json("llm-traces/")] == [1, 2]
    backend._client.list_blobs.assert_called_once_with(BUCKET, prefix="llm-traces/")
