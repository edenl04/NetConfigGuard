from __future__ import annotations

import os
from pathlib import Path


class LockError(RuntimeError):
    pass


class ProjectLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._acquired = False

    def __enter__(self) -> "ProjectLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(self.path), flags)
        except FileExistsError as exc:
            raise LockError(f"Another netconfigguard command is already running: {self.path}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid: {os.getpid()}\n")
        self._acquired = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._acquired:
            try:
                self.path.unlink()
            finally:
                self._acquired = False

