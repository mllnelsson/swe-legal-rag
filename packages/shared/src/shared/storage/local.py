from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import IO, Any

from shared.storage._json import dumps_record, loads_record
from shared.storage.base import DEFAULT_SIGNED_URL_TTL, JSON_STREAM_SUFFIX

# Appending to a stream file is not safe without an exclusive lock. O_APPEND
# guarantees atomicity only for writes below PIPE_BUF (4096 bytes on Linux),
# and a trace record carrying a full document runs to tens of kilobytes —
# concurrent workers would interleave partial lines and corrupt the stream.
# flock is held per open file description, so opening the file per write
# serializes across processes as well as threads.
_flock: Callable[[int, int], None] | None
_LOCK_EXCLUSIVE: int
_LOCK_RELEASE: int

try:
    from fcntl import LOCK_EX, LOCK_UN, flock

    _flock, _LOCK_EXCLUSIVE, _LOCK_RELEASE = flock, LOCK_EX, LOCK_UN
except ImportError:  # pragma: no cover - Windows has no fcntl
    _flock, _LOCK_EXCLUSIVE, _LOCK_RELEASE = None, 0, 0

# Guards the append within one process. Without fcntl this is the only lock
# available, so multi-process local storage requires a POSIX host.
_process_local_lock = threading.Lock()


def _lock_exclusive(handle: IO[bytes]) -> None:
    if _flock is not None:
        _flock(handle.fileno(), _LOCK_EXCLUSIVE)


def _unlock(handle: IO[bytes]) -> None:
    if _flock is not None:
        _flock(handle.fileno(), _LOCK_RELEASE)


class LocalStorageBackend:
    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    def store(self, key: str, data: bytes) -> str:
        target = self._base_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target.absolute())

    def retrieve(self, key: str) -> bytes:
        target = self._base_path / key
        if not target.exists():
            raise FileNotFoundError(f"Key not found: {key}")
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        return (self._base_path / key).exists()

    def delete(self, key: str) -> None:
        (self._base_path / key).unlink(missing_ok=True)

    def get_url(self, key: str, expires_in: int = DEFAULT_SIGNED_URL_TTL) -> str:
        return str((self._base_path / key).absolute())

    def add_json(self, key: str, record: Mapping[str, Any]) -> str:
        target = self._stream_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        line = dumps_record(record) + b"\n"

        with _process_local_lock, open(target, "ab") as handle:
            _lock_exclusive(handle)
            try:
                handle.write(line)
                handle.flush()
            finally:
                _unlock(handle)

        return str(target.absolute())

    def iter_json(self, prefix: str) -> Iterator[Mapping[str, Any]]:
        for path in sorted(self._stream_paths(prefix)):
            with open(path, "rb") as handle:
                for line in handle:
                    if line.strip():
                        yield loads_record(line)

    def _stream_path(self, key: str) -> Path:
        return self._base_path / f"{key}{JSON_STREAM_SUFFIX}"

    def _stream_paths(self, prefix: str) -> Iterator[Path]:
        for path in self._base_path.rglob(f"*{JSON_STREAM_SUFFIX}"):
            key = str(path.relative_to(self._base_path).as_posix())
            if key.removesuffix(JSON_STREAM_SUFFIX).startswith(prefix):
                yield path
