"""Load and validate bot configuration."""

import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, SecretStr, field_serializer

from leadleboard.models import DataModel


class Config(DataModel):
    """Runtime settings loaded from environment variables."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    token: SecretStr = Field(exclude=True, repr=False)
    guild_id: int
    channel_id: int
    timezone: ZoneInfo
    report_time: time
    state_path: Path

    @field_serializer("timezone")
    def serialize_timezone(self, zone: ZoneInfo) -> str:
        """Serialize the timezone name."""
        return zone.key

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
            timezone = ZoneInfo(os.getenv("LEADLEBOARD_TIMEZONE", "America/Chicago"))
        except ZoneInfoNotFoundError as error:
            raise ValueError("LEADLEBOARD_TIMEZONE is not a valid timezone") from error

        try:
            hour_text, minute_text = os.getenv("LEADLEBOARD_REPORT_TIME", "21:00").split(
                ":", maxsplit=1
            )
            report_time = time(hour=int(hour_text), minute=int(minute_text))
        except ValueError as error:
            raise ValueError("LEADLEBOARD_REPORT_TIME must use HH:MM") from error

        try:
            guild_id = int(required["DISCORD_GUILD_ID"] or "")
            channel_id = int(required["DISCORD_CHANNEL_ID"] or "")
        except ValueError as error:
            raise ValueError("DISCORD_GUILD_ID and DISCORD_CHANNEL_ID must be integers") from error

        state_path = Path(os.getenv("LEADLEBOARD_STATE_PATH", ".data/post-state.json")).expanduser()
        return cls(
            token=SecretStr(required["DISCORD_TOKEN"] or ""),
            guild_id=guild_id,
            channel_id=channel_id,
            timezone=timezone,
            report_time=report_time,
            state_path=state_path,
        )
