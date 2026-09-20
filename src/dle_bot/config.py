"""Load and validate bot configuration."""

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime settings loaded from environment variables."""

    token: str
    guild_id: int
    channel_id: int
    timezone: ZoneInfo
    report_time: time
    state_path: Path

    @classmethod
    def load(cls) -> Config:
        """Load settings from `.env` and the process environment."""
        load_dotenv()

        required = {
            "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
            "DISCORD_GUILD_ID": os.getenv("DISCORD_GUILD_ID"),
            "DISCORD_CHANNEL_ID": os.getenv("DISCORD_CHANNEL_ID"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

        try:
            timezone = ZoneInfo(os.getenv("DLE_TIMEZONE", "America/Chicago"))
        except ZoneInfoNotFoundError as error:
            raise ValueError("DLE_TIMEZONE is not a valid timezone") from error

        report_time_text = os.getenv("DLE_REPORT_TIME", "21:00")
        try:
            hour_text, minute_text = report_time_text.split(":", maxsplit=1)
            report_time = time(hour=int(hour_text), minute=int(minute_text))
            ids = {
                name: int(value or "")
                for name, value in required.items()
                if name != "DISCORD_TOKEN"
            }
        except ValueError as error:
            raise ValueError("IDs must be integers and DLE_REPORT_TIME must use HH:MM") from error

        state_path = Path(os.getenv("DLE_STATE_PATH", ".data/post-state")).expanduser()
        return cls(
            token=required["DISCORD_TOKEN"] or "",
            guild_id=ids["DISCORD_GUILD_ID"],
            channel_id=ids["DISCORD_CHANNEL_ID"],
            timezone=timezone,
            report_time=report_time,
            state_path=state_path,
        )
