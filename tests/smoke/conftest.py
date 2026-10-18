"""Prevent live smoke tests from sending Discord messages."""

from unittest.mock import AsyncMock

import discord
import pytest


@pytest.fixture(autouse=True)
def block_discord_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if a Discord message is sent."""
    for channel_type in (discord.TextChannel, discord.Thread, discord.DMChannel):
        monkeypatch.setattr(
            channel_type,
            "send",
            AsyncMock(side_effect=AssertionError("Smoke tests must not send Discord messages")),
        )
