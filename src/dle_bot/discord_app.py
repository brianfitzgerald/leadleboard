"""Read score threads and publish reports through Discord."""

import io
from collections.abc import Awaitable, Callable
from datetime import UTC
from typing import cast

import discord
import httpx

from dle_bot.config import Config
from dle_bot.models import Game, Score, WeeklyReport
from dle_bot.parsers import parse_dartwords, parse_rngdle, parse_size_it_up
from dle_bot.report import render_text, report_marker, report_sections
from dle_bot.schedule import ReportingPeriod
from dle_bot.scoring import build_report


class ActionClient[T](discord.Client):
    """Run one action after Discord is ready, then disconnect."""

    def __init__(self, action: Callable[[discord.Client], Awaitable[T]]) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
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
    await client.start(token)
    if client.error is not None:
        raise client.error
    return cast(T, client.result)


async def fetch_parent(client: discord.Client, config: Config) -> discord.TextChannel:
    """Fetch and validate the configured report channel."""
    channel = await client.fetch_channel(config.channel_id)
    if not isinstance(channel, discord.TextChannel):
        raise RuntimeError("DISCORD_CHANNEL_ID must identify a text channel")
    if channel.guild.id != config.guild_id:
        raise RuntimeError("The report channel is not in DISCORD_GUILD_ID")
    return channel


async def collect_report(
    client: discord.Client,
    config: Config,
    period: ReportingPeriod,
) -> WeeklyReport:
    """Read configured threads and build one weekly report."""
    scores: list[Score] = []
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        for game, thread_id in config.thread_ids.items():
            channel = await client.fetch_channel(thread_id)
            if not isinstance(channel, discord.Thread):
                raise RuntimeError(f"{game.value} ID must identify a Discord thread")
            if channel.guild.id != config.guild_id or channel.parent_id != config.channel_id:
                raise RuntimeError(f"{game.value} thread is not under the configured channel")

            async for message in channel.history(
                after=period.start.astimezone(UTC),
                before=period.end.astimezone(UTC),
                oldest_first=True,
                limit=None,
            ):
                if message.author.bot:
                    continue
                if game is Game.SIZE_IT_UP:
                    value = parse_size_it_up(message.content)
                elif game is Game.RNGDLE:
                    value = parse_rngdle(message.content)
                else:
                    descriptions = [
                        embed.description
                        for embed in message.embeds
                        if embed.description is not None
                    ]
                    value = await parse_dartwords(message.content, descriptions, http_client)
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
    report: WeeklyReport,
    period: ReportingPeriod,
) -> int | None:
    """Find this bot's existing report marker in Discord."""
    if client.user is None:
        raise RuntimeError("Discord did not provide the bot user")
    marker = report_marker(report)
    async for message in channel.history(after=period.end.astimezone(UTC), limit=None):
        if message.author.id == client.user.id and message.content == marker:
            return message.id
    return None


async def publish_report(channel: discord.TextChannel, report: WeeklyReport) -> discord.Message:
    """Post one report message or a text attachment when it is large."""
    marker = report_marker(report)
    text = render_text(report)
    embed = discord.Embed(title=marker, color=discord.Color.blue())
    total_length = len(marker)
    field_count = 0
    for title, lines in report_sections(report):
        chunks: list[str] = []
        current = ""
        for line in lines:
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > 1000:
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

    if total_length <= 5800 and field_count <= 25:
        return await channel.send(content=marker, embed=embed)

    attachment = discord.File(
        io.BytesIO(text.encode("utf-8")),
        filename=f"high-scores-{report.week_start.isoformat()}.txt",
    )
    return await channel.send(content=marker, file=attachment)


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
    required = {
        "View Channels": permissions.view_channel,
        "Read Message History": permissions.read_message_history,
        "Send Messages": permissions.send_messages,
        "Embed Links": permissions.embed_links,
        "Attach Files": permissions.attach_files,
    }
    denied = [name for name, allowed in required.items() if not allowed]
    if denied:
        raise RuntimeError(f"Missing channel permissions: {', '.join(denied)}")

    public_types = {discord.ChannelType.news_thread, discord.ChannelType.public_thread}
    active_threads = await guild.active_threads()
    threads = {
        thread.id: thread
        for thread in active_threads
        if thread.parent_id == parent.id and thread.type in public_types
    }
    async for thread in parent.archived_threads(limit=None):
        threads[thread.id] = thread

    if not threads:
        raise RuntimeError(f"No public threads were found under #{parent.name}")
    for game, thread_id in config.thread_ids.items():
        if thread_id not in threads:
            raise RuntimeError(
                f"{game.value} is not an accessible public thread under #{parent.name}"
            )

    details = [
        f"Guild: {guild.name}",
        f"Report channel: #{parent.name}",
        f"Public threads: {len(threads)}",
    ]
    for thread in sorted(
        threads.values(),
        key=lambda item: (item.archived, item.name.casefold(), item.id),
    ):
        message_count = 0
        async for _ in thread.history(limit=1):
            message_count = 1
            break
        state = "archived" if thread.archived else "active"
        sample = "1 message read" if message_count else "empty"
        details.append(f"{state}: #{thread.name} ({sample})")
    return details
