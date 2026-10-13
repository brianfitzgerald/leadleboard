"""Read score threads and publish reports through Discord."""

import asyncio
import io
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast

import discord
import httpx

from leadleboard.config import Config
from leadleboard.models import Game, Score, WeeklyReport
from leadleboard.parsers import parse_dartwords, parse_rngdle, parse_size_it_up
from leadleboard.report import render_text, report_marker, report_sections
from leadleboard.schedule import ReportingPeriod
from leadleboard.scoring import build_report

REQUIRED_PERMISSIONS = {
    "view_channel": "View Channels",
    "read_message_history": "Read Message History",
    "send_messages": "Send Messages",
    "embed_links": "Embed Links",
    "attach_files": "Attach Files",
}


class ActionClient[T](discord.Client):
    """Run one action after Discord is ready, then disconnect."""

    def __init__(self, action: Callable[[discord.Client], Awaitable[T]]) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.action = action
        self.result: T | None = None
        self.error: Exception | None = None
        self.action_started = False

    async def on_ready(self) -> None:
        """Run the configured action once."""
        if self.action_started:
            return
        self.action_started = True
        try:
            self.result = await self.action(self)
        except Exception as error:
            self.error = error
        finally:
            await self.close()


async def run_discord_action[T](token: str, action: Callable[[discord.Client], Awaitable[T]]) -> T:
    """Connect a short-lived Discord client and return its action result."""
    client = ActionClient(action)
    try:
        async with asyncio.timeout(600):
            await client.start(token)
    except TimeoutError as error:
        await client.close()
        raise RuntimeError("The Discord action did not finish in 10 minutes") from error
    if client.error is not None:
        raise client.error
    if not client.action_started:
        raise RuntimeError("Discord closed the connection before the action started")
    return cast(T, client.result)


async def fetch_parent(client: discord.Client, config: Config) -> discord.TextChannel:
    """Fetch and validate the configured report channel."""
    channel = await client.fetch_channel(config.channel_id)
    if not isinstance(channel, discord.TextChannel):
        raise RuntimeError("DISCORD_CHANNEL_ID must identify a text channel")
    if channel.guild.id != config.guild_id:
        raise RuntimeError("The report channel is not in DISCORD_GUILD_ID")
    return channel


async def discover_public_threads(
    parent: discord.TextChannel,
    guild: discord.Guild,
    after: datetime | None = None,
) -> list[discord.Thread]:
    """Return active public threads and those archived after a time."""
    public_types = {discord.ChannelType.news_thread, discord.ChannelType.public_thread}
    active_threads = await guild.active_threads()
    threads = {
        thread.id: thread
        for thread in active_threads
        if thread.parent_id == parent.id and thread.type in public_types
    }
    async for thread in parent.archived_threads(limit=None):
        # Discord returns archived threads newest first.
        if after is not None and thread.archive_timestamp < after:
            break
        threads[thread.id] = thread
    return sorted(
        threads.values(),
        key=lambda item: (item.archived, item.name.casefold(), item.id),
    )


async def collect_report(parent: discord.TextChannel, period: ReportingPeriod) -> WeeklyReport:
    """Read the parent and its public threads and build a weekly report."""
    channels: list[discord.TextChannel | discord.Thread] = [
        parent,
        *await discover_public_threads(parent, parent.guild, after=period.start),
    ]
    scores: list[Score] = []
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        for channel in channels:
            async for message in channel.history(
                after=period.start.astimezone(UTC),
                before=period.end.astimezone(UTC),
                oldest_first=True,
                limit=None,
            ):
                if message.author.bot:
                    continue
                descriptions = [
                    embed.description for embed in message.embeds if embed.description is not None
                ]
                values = {
                    Game.SIZE_IT_UP: parse_size_it_up(message.content),
                    Game.RNGDLE: parse_rngdle(message.content),
                    Game.DARTWORDS: await parse_dartwords(
                        message.content,
                        descriptions,
                        http_client,
                    ),
                }
                for game, value in values.items():
                    if value is None:
                        continue
                    scores.append(
                        Score(
                            user_id=message.author.id,
                            display_name=message.author.display_name,
                            game=game,
                            value=value,
                        )
                    )

    return build_report(scores, period.week_start, period.week_end)


async def find_existing_report(
    client: discord.Client,
    channel: discord.TextChannel,
    period: ReportingPeriod,
) -> int | None:
    """Find this bot's existing report marker in Discord."""
    if client.user is None:
        raise RuntimeError("Discord did not provide the bot user")
    marker = report_marker(period.week_start, period.week_end)
    async for message in channel.history(after=period.end.astimezone(UTC), limit=None):
        if message.author.id == client.user.id and message.content == marker:
            return message.id
    return None


async def publish_report(channel: discord.TextChannel, report: WeeklyReport) -> discord.Message:
    """Post one report message or a text attachment when it is large."""
    marker = report_marker(report.week_start, report.week_end)
    text = render_text(report)
    sections = report_sections(report, markdown=True)
    oversized = any(len(line) > 1000 for _, lines in sections for line in lines)
    embed = discord.Embed(color=discord.Color.gold())
    total_length = len(marker)
    field_count = 0
    for title, lines in sections:
        chunks: list[str] = []
        current = ""
        for line in lines:
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > 1000:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)
        for index, chunk in enumerate(chunks):
            field_title = title if index == 0 else f"{title} continued"
            embed.add_field(name=field_title, value=chunk, inline=False)
            total_length += len(field_title) + len(chunk)
            field_count += 1

    no_mentions = discord.AllowedMentions.none()
    if not oversized and total_length <= 5800 and field_count <= 25:
        return await channel.send(content=marker, embed=embed, allowed_mentions=no_mentions)

    attachment = discord.File(
        io.BytesIO(text.encode("utf-8")),
        filename=f"high-scores-{report.week_start.isoformat()}.txt",
    )
    return await channel.send(content=marker, file=attachment, allowed_mentions=no_mentions)


async def check_access(client: discord.Client, config: Config) -> list[str]:
    """Validate permissions and read all public thread histories."""
    guild = client.get_guild(config.guild_id)
    if guild is None:
        raise RuntimeError("The bot is not a member of DISCORD_GUILD_ID")
    parent = await fetch_parent(client, config)
    member = guild.me
    if member is None:
        raise RuntimeError("The bot member is not available")
    permissions = parent.permissions_for(member)
    denied = [
        label for name, label in REQUIRED_PERMISSIONS.items() if not getattr(permissions, name)
    ]
    if denied:
        raise RuntimeError(f"Missing channel permissions: {', '.join(denied)}")

    threads = await discover_public_threads(parent, guild)

    samples: list[str] = []
    for channel in (parent, *threads):
        sample = "empty"
        async for _ in channel.history(limit=1):
            sample = "1 message read"
        samples.append(sample)

    details = [
        f"Guild: {guild.name}",
        f"Report channel: #{parent.name} ({samples[0]})",
        f"Public threads: {len(threads)}",
    ]
    for thread, sample in zip(threads, samples[1:], strict=True):
        state = "archived" if thread.archived else "active"
        details.append(f"{state}: #{thread.name} ({sample})")

    for other in client.guilds:
        if other.id != guild.id:
            details.append(f"Warning: the bot is also in the guild {other.name}")
    for channel in guild.channels:
        if channel.id == parent.id or isinstance(channel, discord.CategoryChannel):
            continue
        if channel.permissions_for(member).view_channel:
            details.append(f"Warning: the bot can view #{channel.name}")
    required = discord.Permissions(**dict.fromkeys(REQUIRED_PERMISSIONS, True))
    for role in member.roles:
        if role.is_default():
            continue
        extra = [
            name for name, allowed in role.permissions if allowed and not getattr(required, name)
        ]
        if extra:
            details.append(f"Warning: the role {role.name} also grants {', '.join(extra)}")
    return details
