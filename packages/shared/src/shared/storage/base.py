from collections.abc import Iterator, Mapping
from typing import Any, Protocol, runtime_checkable

# Default lifetime (seconds) of a signed download URL: one hour.
DEFAULT_SIGNED_URL_TTL = 3600

# Suffix a local backend appends to a logical stream key.
JSON_STREAM_SUFFIX = ".jsonl"


@runtime_checkable
class StorageBackend(Protocol):
    def store(self, key: str, data: bytes) -> str: ...

    def retrieve(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def get_url(self, key: str, expires_in: int = DEFAULT_SIGNED_URL_TTL) -> str: ...

    def add_json(self, key: str, record: Mapping[str, Any]) -> str:
        """Append one JSON record to the stream at `key`, returning its location.

        `key` is an extension-free *logical stream key* ("llm-traces/2026-07-27"),
        not a file name. How a stream is physically laid out is the backend's
        business and deliberately differs: a local backend appends a line to one
        file, while an object store — which cannot append — mints a new object
        per record. Callers never see the difference; they write with `add_json`
        and read with `iter_json`.

        Records within a stream are unordered. Key order approximates write order
        on an object store and completion order locally, but neither is a total
        order: anything that cares must sort on a field of the record itself.
        """
        ...

    def iter_json(self, prefix: str) -> Iterator[Mapping[str, Any]]:
        """Yield every record from every stream whose key starts with `prefix`.

        The read counterpart of `add_json`, and the only way to read a stream
        back without knowing how the backend laid it out.
        """
        ...
