from __future__ import annotations

import hashlib
import shutil
import tempfile
import threading
from pathlib import Path


class LineAudioCache:
    """Own a temporary, deterministic MP3 cache for repeated line playback."""

    def __init__(self, prefix: str = "gpt01_ab_cache_") -> None:
        self.prefix = prefix
        self._directory: Path | None = None
        self._lock = threading.RLock()

    @property
    def directory(self) -> Path | None:
        return self._directory

    @property
    def has_files(self) -> bool:
        with self._lock:
            return bool(self._directory and any(self._directory.glob("*.mp3")))

    def path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        with self._lock:
            if self._directory is None:
                self._directory = Path(tempfile.mkdtemp(prefix=self.prefix))
            return self._directory / f"{digest}.mp3"

    def get(self, key: str) -> Path | None:
        path = self.path_for(key)
        try:
            return path if path.is_file() and path.stat().st_size > 0 else None
        except OSError:
            return None

    def discard(self, key: str) -> None:
        try:
            self.path_for(key).unlink(missing_ok=True)
        except OSError:
            pass

    def contains(self, path: Path | None) -> bool:
        if path is None or self._directory is None:
            return False
        try:
            return path.resolve().parent == self._directory.resolve()
        except OSError:
            return False

    def clear(self) -> None:
        with self._lock:
            directory = self._directory
            self._directory = None
        if directory:
            shutil.rmtree(directory, ignore_errors=True)
