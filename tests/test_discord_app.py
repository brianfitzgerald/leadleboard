from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import discord
import pytest

import dle_bot.discord_app as discord_app
from dle_bot.config import Config
from dle_bot.discord_app import check_access, collect_report, find_existing_report
from dle_bot.models import Game, WeeklyReport
from dle_bot.report import report_marker
from dle_bot.schedule import ReportingPeriod


class FakeThread:
    """Provide the thread data used by access checks."""

    def __init__(
        self,
        thread_id: int,
        name: str,
        thread_type: discord.ChannelType,
        *,
        archived: bool = False,
        has_message: bool = True,
    ) -> None:
        self.id = thread_id
        self.name = name
        self.type = thread_type
        self.archived = archived
        self.parent_id = 10
        self.has_message = has_message

    async def history(self, **kwargs: object) -> AsyncIterator[object]:
        if self.has_message:
            yield object()


class FakeParent:
    """Provide permissions and archived threads for access checks."""

    id = 10
    name = "games"

    def __init__(
        self,
        archived: list[FakeThread],
        *,
        attach_files: bool = True,
        has_message: bool = True,
    ) -> None:
        self.archived = archived
        self.attach_files = attach_files
        self.has_message = has_message

    def permissions_for(self, member: object) -> SimpleNamespace:
        return SimpleNamespace(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            embed_links=True,
            attach_files=self.attach_files,
        )

    async def archived_threads(self, **kwargs: object) -> AsyncIterator[FakeThread]:
        for thread in self.archived:
            yield thread

    async def history(self, **kwargs: object) -> AsyncIterator[object]:
        if self.has_message:
            yield object()


class FakeGuild:
    """Provide active threads for access checks."""

    name = "Friends"
    me = object()

    def __init__(self, active: list[FakeThread]) -> None:
        self.active = active

    async def active_threads(self) -> list[FakeThread]:
        return self.active


def config() -> Config:
    """Build test configuration."""
    return Config(
        token="token",
        guild_id=1,
        channel_id=10,
        timezone=ZoneInfo("America/Chicago"),
        report_time=time(21),
        state_path=Path("state"),
    )


async def run_access_check(
    monkeypatch: pytest.MonkeyPatch,
    parent: FakeParent,
    guild: FakeGuild,
    settings: Config,
) -> list[str]:
    """Run the access check with Discord test objects."""

    async def fetch_parent(client: discord.Client, current: Config) -> discord.TextChannel:
        return cast(discord.TextChannel, parent)

    monkeypatch.setattr(discord_app, "fetch_parent", fetch_parent)
    client = cast(discord.Client, SimpleNamespace(get_guild=lambda guild_id: guild))
    return await check_access(client, settings)


@pytest.mark.parametrize(("author_id", "expected"), [(42, 123), (9, None)])
async def test_find_existing_report(author_id: int, expected: int | None) -> None:
    class HistoryChannel:
        """Provide the history interface used by duplicate detection."""

        async def history(self, **kwargs: object) -> AsyncIterator[SimpleNamespace]:
            yield SimpleNamespace(
                id=123,
                author=SimpleNamespace(id=author_id),
                content=report_marker(report),
            )

    report = WeeklyReport(
        week_start=date(2026, 9, 14),
        week_end=date(2026, 9, 20),
        games={},
        overall=[],
    )
    period = ReportingPeriod(
        start=datetime(2026, 9, 14, tzinfo=UTC),
        end=datetime(2026, 9, 21, tzinfo=UTC),
    )
    client = cast(discord.Client, SimpleNamespace(user=SimpleNamespace(id=42)))
    channel = cast(discord.TextChannel, HistoryChannel())

    assert await find_existing_report(client, channel, report, period) == expected


async def test_check_access_reads_all_public_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    active = [
        FakeThread(11, "Size It Up", discord.ChannelType.public_thread),
        FakeThread(12, "RNGdle", discord.ChannelType.news_thread, has_message=False),
        FakeThread(13, "Dartwords", discord.ChannelType.public_thread),
        FakeThread(99, "Private", discord.ChannelType.private_thread),
    ]
    archived = [FakeThread(13, "Dartwords", discord.ChannelType.public_thread, archived=True)]

    details = await run_access_check(
        monkeypatch,
        FakeParent(archived),
        FakeGuild(active),
        config(),
    )

    assert "Report channel: #games (1 message read)" in details
    assert "Public threads: 3" in details
    assert "active: #Size It Up (1 message read)" in details
    assert "active: #RNGdle (empty)" in details
    assert "archived: #Dartwords (1 message read)" in details
    assert all("Private" not in detail for detail in details)


async def test_check_access_requires_attach_files(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="Attach Files"):
        await run_access_check(
            monkeypatch,
            FakeParent([], attach_files=False),
            FakeGuild([]),
            config(),
        )


async def test_check_access_allows_no_public_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    private = [FakeThread(99, "Private", discord.ChannelType.private_thread)]

    details = await run_access_check(
        monkeypatch,
        FakeParent([], has_message=False),
        FakeGuild(private),
        config(),
    )

    assert "Report channel: #games (empty)" in details
    assert "Public threads: 0" in details


async def test_collect_report_parses_each_game_from_any_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=42, display_name="Ada", bot=False)
    bot = SimpleNamespace(id=7, display_name="Bot", bot=True)
    combined = SimpleNamespace(
        author=user,
        content=(
            "Size It Up\nOverall Score 254\nhttps://magnitudle.com/size-it-up\n"
            "RNGdle 🎲 122228\n203,506 EP\nhttps://rngdle.com"
        ),
        embeds=[],
    )
    dartwords = SimpleNamespace(
        author=user,
        content="https://www.dartwords.com/share?id=tl7i9vhphy",
        embeds=[SimpleNamespace(description="I solved today's Dartwords in 5 guesses!")],
    )
    ignored = SimpleNamespace(
        author=bot,
        content="Size It Up\nOverall Score 500\nhttps://magnitudle.com/size-it-up",
        embeds=[],
    )

    class HistoryChannel:
        """Provide messages for report collection."""

        def __init__(self, messages: list[SimpleNamespace]) -> None:
            self.messages = messages
            self.guild = SimpleNamespace()

        async def history(self, **kwargs: object) -> AsyncIterator[SimpleNamespace]:
            for message in self.messages:
                yield message

    parent = HistoryChannel([combined, ignored])
    thread = HistoryChannel([dartwords])

    async def fetch_parent(client: discord.Client, current: Config) -> discord.TextChannel:
        return cast(discord.TextChannel, parent)

    async def discover_threads(
        current: discord.TextChannel,
        guild: discord.Guild,
    ) -> list[discord.Thread]:
        return [cast(discord.Thread, thread)]

    monkeypatch.setattr(discord_app, "fetch_parent", fetch_parent)
    monkeypatch.setattr(discord_app, "discover_public_threads", discover_threads)
    period = ReportingPeriod(
        start=datetime(2026, 9, 14, tzinfo=UTC),
        end=datetime(2026, 9, 21, tzinfo=UTC),
    )

    report = await collect_report(cast(discord.Client, object()), config(), period)

    assert report.games[Game.SIZE_IT_UP][0].score.value == 254
    assert report.games[Game.RNGDLE][0].score.value == 203506
    assert report.games[Game.DARTWORDS][0].score.value == 5
    assert report.overall[0].display_name == "Ada"
