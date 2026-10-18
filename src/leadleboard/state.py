"""Protect JSON post history with a separate lock file."""

import fcntl
import os
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import TracebackType
from typing import Self, TextIO

from leadleboard.models import PostHistory, PostRecord


class PostState:
    """Store report history and serialize local post attempts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.history = PostHistory()
        self._lock: TextIO | None = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = self.path.with_name(f"{self.path.name}.lock").open("a", encoding="utf-8")
        try:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._lock.close()
            self._lock = None
            raise RuntimeError("Another run holds the post state lock") from error
        try:
            if self.path.exists():
                self.history = PostHistory.model_validate_json(
                    self.path.read_text(encoding="utf-8")
                )
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._lock is not None:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
            self._lock.close()
            self._lock = None

    def was_posted(self, week_start: date, guild_id: int, channel_id: int) -> bool:
        """Check scoped records and existing imported dates."""
        if self._lock is None:
            raise RuntimeError("Post state is not locked")
        return any(
            record.week_start == week_start
            and (
                (record.guild_id == guild_id and record.channel_id == channel_id)
                or record.outcome == "imported"
            )
            for record in self.history.records
        )

    def record(
        self,
        week_start: date,
        guild_id: int,
        channel_id: int,
        message_id: int,
        posted: bool,
    ) -> None:
        """Record a successful post or a report found in Discord."""
        if self.was_posted(week_start, guild_id, channel_id):
            return
        record = PostRecord(
            week_start=week_start,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            recorded_at=datetime.now(UTC),
            outcome="posted" if posted else "found",
        )
        history = PostHistory(records=[*self.history.records, record])
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.path.parent, delete=False
        ) as file:
            temporary_path = Path(file.name)
            try:
                file.write(history.model_dump_json(indent=2) + "\n")
                file.flush()
                os.fsync(file.fileno())
                os.replace(temporary_path, self.path)
            finally:
                temporary_path.unlink(missing_ok=True)
        self.history = history
