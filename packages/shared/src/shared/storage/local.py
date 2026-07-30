from pathlib import Path

from shared.storage.base import DEFAULT_SIGNED_URL_TTL


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
