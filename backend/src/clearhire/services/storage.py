"""CV files on disk, addressed by their SHA-256 (the same file uploaded twice is stored once)."""

from __future__ import annotations

import hashlib
from pathlib import Path


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, data: bytes) -> tuple[str, str]:
        """Store the bytes; returns (storage key, sha256)."""
        digest = hashlib.sha256(data).hexdigest()
        key = f"{digest[:2]}/{digest}"
        path = self.root / key
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)  # atomic: a crash never leaves half a file under the final name
        return key, digest

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("storage key outside the store")
        return path
