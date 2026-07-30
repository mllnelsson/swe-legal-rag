from typing import Protocol, runtime_checkable

# Default lifetime (seconds) of a signed download URL: one hour.
DEFAULT_SIGNED_URL_TTL = 3600


@runtime_checkable
class StorageBackend(Protocol):
    def store(self, key: str, data: bytes) -> str: ...

    def retrieve(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def get_url(self, key: str, expires_in: int = DEFAULT_SIGNED_URL_TTL) -> str: ...
