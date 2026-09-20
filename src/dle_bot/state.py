"""Protect weekly posts with a locked state file."""

import fcntl
from datetime import date
from pathlib import Path
from types import TracebackType
from typing import IO, Self


class PostState:
    """Store posted weeks and serialize local post attempts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: IO[str] | None = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+", encoding="utf-8")
        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is not None:
            self._file.flush()
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None

    def was_posted(self, week_start: date) -> bool:
        """Return whether the week has a successful post."""
        if self._file is None:
            raise RuntimeError("Post state is not locked")
        self._file.seek(0)
        return self._file.read().strip() == week_start.isoformat()

    def record(self, week_start: date) -> None:
        """Record one successful weekly post."""
        if self._file is None:
            raise RuntimeError("Post state is not locked")
        self._file.seek(0)
        self._file.truncate()
        self._file.write(week_start.isoformat())
