"""Read score threads and publish reports through Discord."""

import asyncio
import io
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast

import discord
import httpx

from leadleboard.config import Config
from leadleboard.models import Game, ReportingPeriod, Score, WeeklyReport
from leadleboard.parsers import parse_dartwords, parse_rngdle, parse_size_it_up, parse_wikirng
from leadleboard.report import build_message_payload, report_marker
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
        async with client, asyncio.timeout(600):
            await client.start(token)
    except TimeoutError as error:
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
                    Game.WIKIRNG: parse_wikirng(message.content),
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
                            avatar_url=message.author.display_avatar.replace(
                                size=512, static_format="png"
                            ).url,
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


async def publish_report(
    channel: discord.TextChannel,
    report: WeeklyReport,
    image: bytes | None = None,
) -> discord.Message:
    """Post one report message with the highlight image, or a text attachment when it is large."""
    payload = build_message_payload(report, image=image is not None)
    no_mentions = discord.AllowedMentions.none()
    files: list[discord.File] = []
    if image is not None and payload.image_filename is not None:
        files.append(discord.File(io.BytesIO(image), filename=payload.image_filename))
    if payload.embed is not None:
        embed = discord.Embed.from_dict(payload.embed.model_dump(exclude_none=True))
        return await channel.send(
            content=payload.content, embed=embed, files=files, allowed_mentions=no_mentions
        )
    if payload.attachment is None:
        raise RuntimeError("The report payload has no embed or attachment")
    files.insert(
        0,
        discord.File(
            io.BytesIO(payload.attachment.text.encode("utf-8")),
            filename=payload.attachment.filename,
        ),
    )
    return await channel.send(content=payload.content, files=files, allowed_mentions=no_mentions)


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
