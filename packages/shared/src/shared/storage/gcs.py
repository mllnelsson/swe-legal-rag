from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from shared.storage._json import dumps_record, loads_record
from shared.storage.base import DEFAULT_SIGNED_URL_TTL

try:
    from google.cloud import storage as gcs_storage
except ImportError:
    gcs_storage = None  # type: ignore[assignment]

# One JSON record per object, since object stores cannot append. The
# microsecond timestamp makes lexicographic key order approximate write order;
# the random suffix keeps keys unique when two processes write in the same
# microsecond.
_RECORD_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%f"
_RECORD_SUFFIX_LENGTH = 8
_RECORD_CONTENT_TYPE = "application/json"


class GCSStorageBackend:
    def __init__(self, bucket_name: str) -> None:
        if gcs_storage is None:
            raise ImportError(
                "google-cloud-storage is not installed. "
                "Install it with: pip install 'shared[gcs]' or "
                "pip install google-cloud-storage>=2.0"
            )
        self._bucket_name = bucket_name
        self._client = gcs_storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def store(self, key: str, data: bytes) -> str:
        blob = self._bucket.blob(key)
        blob.upload_from_string(data)
        return f"gs://{self._bucket_name}/{key}"

    def retrieve(self, key: str) -> bytes:
        blob = self._bucket.blob(key)
        return blob.download_as_bytes()

    def exists(self, key: str) -> bool:
        blob = self._bucket.blob(key)
        return blob.exists()

    def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)
        blob.delete()

    def get_url(self, key: str, expires_in: int = DEFAULT_SIGNED_URL_TTL) -> str:
        blob = self._bucket.blob(key)
        return blob.generate_signed_url(expiration=timedelta(seconds=expires_in))

    def add_json(self, key: str, record: Mapping[str, Any]) -> str:
        object_key = f"{key}/{_record_object_name()}"
        blob = self._bucket.blob(object_key)
        blob.upload_from_string(dumps_record(record), content_type=_RECORD_CONTENT_TYPE)
        return f"gs://{self._bucket_name}/{object_key}"

    def iter_json(self, prefix: str) -> Iterator[Mapping[str, Any]]:
        blobs = self._client.list_blobs(self._bucket_name, prefix=prefix)
        for blob in sorted(blobs, key=lambda b: b.name):
            yield loads_record(blob.download_as_bytes())


def _record_object_name() -> str:
    timestamp = datetime.now(UTC).strftime(_RECORD_TIMESTAMP_FORMAT)
    suffix = uuid.uuid4().hex[:_RECORD_SUFFIX_LENGTH]
    return f"{timestamp}Z-{suffix}.json"
