from datetime import timedelta

from shared.storage.base import DEFAULT_SIGNED_URL_TTL

try:
    from google.cloud import storage as gcs_storage
except ImportError:
    gcs_storage = None  # type: ignore[assignment]


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
