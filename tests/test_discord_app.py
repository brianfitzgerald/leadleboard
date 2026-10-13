from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import discord
import pytest

import leadleboard.discord_app as discord_app
from leadleboard.config import Config
from leadleboard.discord_app import (
    check_access,
    collect_report,
    discover_public_threads,
    find_existing_report,
    publish_report,
    run_discord_action,
)
from leadleboard.models import Game, Score
from leadleboard.report import report_marker
from leadleboard.schedule import ReportingPeriod
from leadleboard.scoring import build_report

PERIOD = ReportingPeriod(
    week_start=date(2026, 9, 14),
    start=datetime(2026, 9, 13, 21, tzinfo=UTC),
    end=datetime(2026, 9, 20, 21, tzinfo=UTC),
)


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
        archive_timestamp: datetime | None = None,
    ) -> None:
        self.archive_timestamp = archive_timestamp
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

    id = 1
    name = "Friends"

    def __init__(
        self,
        active: list[FakeThread],
        *,
        channels: list[object] | None = None,
        role_permissions: discord.Permissions | None = None,
    ) -> None:
        self.active = active
        self.channels = channels or []
        self.me = SimpleNamespace(
            roles=[
                SimpleNamespace(name="@everyone", is_default=lambda: True),
                SimpleNamespace(
                    name="leadleboard",
                    is_default=lambda: False,
                    permissions=role_permissions or discord.Permissions.none(),
                ),
            ]
        )

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
    other_guilds: list[SimpleNamespace] | None = None,
) -> list[str]:
    """Run the access check with Discord test objects."""

    async def fetch_parent(client: discord.Client, current: Config) -> discord.TextChannel:
        return cast(discord.TextChannel, parent)

    monkeypatch.setattr(discord_app, "fetch_parent", fetch_parent)
    client = cast(
        discord.Client,
        SimpleNamespace(get_guild=lambda guild_id: guild, guilds=[guild, *(other_guilds or [])]),
    )
    return await check_access(client, settings)


@pytest.mark.parametrize(("author_id", "expected"), [(42, 123), (9, None)])
async def test_find_existing_report(author_id: int, expected: int | None) -> None:
    class HistoryChannel:
        """Provide the history interface used by duplicate detection."""

        async def history(self, **kwargs: object) -> AsyncIterator[SimpleNamespace]:
            yield SimpleNamespace(
                id=123,
                author=SimpleNamespace(id=author_id),
                content=report_marker(date(2026, 9, 14), date(2026, 9, 20)),
            )

    client = cast(discord.Client, SimpleNamespace(user=SimpleNamespace(id=42)))
    channel = cast(discord.TextChannel, HistoryChannel())

    assert await find_existing_report(client, channel, PERIOD) == expected


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

    async def discover_threads(
        current: discord.TextChannel,
        guild: discord.Guild,
        after: datetime | None = None,
    ) -> list[discord.Thread]:
        return [cast(discord.Thread, thread)]

    monkeypatch.setattr(discord_app, "discover_public_threads", discover_threads)

    report = await collect_report(cast(discord.TextChannel, parent), PERIOD)

    assert report.games[Game.SIZE_IT_UP][0].score.value == 254
    assert report.games[Game.RNGDLE][0].score.value == 203506
    assert report.games[Game.DARTWORDS][0].score.value == 5
    assert report.overall[0].display_name == "Ada"


@pytest.mark.parametrize(
    ("channels", "other_guilds", "role_permissions", "expected"),
    [
        ([], [], discord.Permissions.none(), []),
        ([SimpleNamespace(id=20, name="general", visible=False)], [], None, []),
        (
            [SimpleNamespace(id=20, name="general", visible=True)],
            [],
            None,
            ["Warning: the bot can view #general"],
        ),
        (
            [],
            [SimpleNamespace(id=2, name="Other")],
            None,
            ["Warning: the bot is also in the guild Other"],
        ),
        (
            [],
            [],
            discord.Permissions(view_channel=True, send_messages=True, administrator=True),
            ["Warning: the role leadleboard also grants administrator"],
        ),
    ],
)
async def test_check_access_warns_about_wider_access(
    monkeypatch: pytest.MonkeyPatch,
    channels: list[SimpleNamespace],
    other_guilds: list[SimpleNamespace],
    role_permissions: discord.Permissions | None,
    expected: list[str],
) -> None:
    parent = FakeParent([])
    for channel in channels:
        channel.permissions_for = lambda member, visible=channel.visible: SimpleNamespace(
            view_channel=visible
        )
    guild = FakeGuild([], channels=[parent, *channels], role_permissions=role_permissions)

    details = await run_access_check(monkeypatch, parent, guild, config(), other_guilds)

    assert [detail for detail in details if detail.startswith("Warning")] == expected


async def test_discover_public_threads_stops_at_old_archived_threads() -> None:
    public = discord.ChannelType.public_thread
    archived = [
        FakeThread(11, "New", public, archived=True, archive_timestamp=PERIOD.end),
        FakeThread(
            12, "Old", public, archived=True, archive_timestamp=datetime(2026, 9, 1, tzinfo=UTC)
        ),
    ]

    threads = await discover_public_threads(
        cast(discord.TextChannel, FakeParent(archived)),
        cast(discord.Guild, FakeGuild([])),
        after=PERIOD.start,
    )

    assert [thread.name for thread in threads] == ["New"]


@pytest.mark.parametrize(
    ("scores", "expect_embed"),
    [
        ([Score(1, "Ada", Game.RNGDLE, 203506)], True),
        ([Score(index, f"Player {index}", Game.RNGDLE, index) for index in range(40)], True),
        ([Score(index, f"Player {index}", Game.RNGDLE, index) for index in range(200)], False),
        ([Score(1, "Ada", Game.RNGDLE, 10**1500)], False),
    ],
)
async def test_publish_report_sends_valid_fields_or_a_file(
    scores: list[Score],
    expect_embed: bool,
) -> None:
    class SendChannel:
        """Record the arguments of one sent message."""

        async def send(self, **kwargs: object) -> None:
            self.sent = kwargs

    channel = SendChannel()
    report = build_report(scores, PERIOD.week_start, PERIOD.week_end)

    await publish_report(cast(discord.TextChannel, channel), report)

    mentions = cast(discord.AllowedMentions, channel.sent["allowed_mentions"])
    assert mentions.to_dict() == discord.AllowedMentions.none().to_dict()
    assert ("embed" in channel.sent) == expect_embed
    assert ("file" in channel.sent) != expect_embed
    if expect_embed:
        embed = cast(discord.Embed, channel.sent["embed"])
        assert all(0 < len(field.value or "") <= 1024 for field in embed.fields)


async def test_run_discord_action_requires_a_started_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def start(self: discord.Client, token: str) -> None:
        return None

    async def action(client: discord.Client) -> int:
        return 1

    monkeypatch.setattr(discord_app.ActionClient, "start", start)

    with pytest.raises(RuntimeError, match="before the action started"):
        await run_discord_action("token", action)
