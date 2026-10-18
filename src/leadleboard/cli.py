"""Python Fire command-line interface."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import discord
import fire

from leadleboard.cards import render_highlights
from leadleboard.config import Config
from leadleboard.discord_app import (
    check_access,
    collect_report,
    fetch_parent,
    find_existing_report,
    publish_report,
    run_discord_action,
)
from leadleboard.models import PostResult, PreviewSnapshot, WeeklyReport
from leadleboard.report import build_message_payload, render_markdown, save_preview
from leadleboard.schedule import (
    ReportingPeriod,
    current_week_start,
    is_post_window,
    period_for_week,
)
from leadleboard.state import PostState


class LeadleboardCli:
    """Collect and report weekly Discord high scores."""

    def check(self) -> None:
        """Validate permissions and public thread history without posting."""
        config = Config.load()

        async def action(client: discord.Client) -> list[str]:
            return await check_access(client, config)

        for line in asyncio.run(run_discord_action(config.token.get_secret_value(), action)):
            print(line)
        print("Configuration, permissions, and public thread access are valid.")

    def preview(self, week: str | int | None = None, output_dir: str | None = None) -> None:
        """Print a weekly report without posting or changing post state."""
        config = Config.load()
        now = datetime.now(config.timezone)
        week_start = current_week_start(now) if week is None else date.fromisoformat(str(week))
        period = period_for_week(
            week_start,
            config.report_time,
            config.timezone,
        )
        if period.start > now:
            raise ValueError("The preview week cannot be in the future")
        if period.end > now:
            period = ReportingPeriod(week_start=week_start, start=period.start, end=now)

        async def action(client: discord.Client) -> WeeklyReport:
            parent = await fetch_parent(client, config)
            return await collect_report(parent, period)

        report = asyncio.run(run_discord_action(config.token.get_secret_value(), action))
        image = asyncio.run(render_highlights(report.highlights))
        snapshot = PreviewSnapshot(
            collected_at=datetime.now(UTC),
            guild_id=config.guild_id,
            channel_id=config.channel_id,
            period=period,
            report=report,
            payload=build_message_payload(report, image=image is not None),
        )
        if output_dir is not None:
            save_preview(snapshot, Path(output_dir), f"high-scores-{week_start.isoformat()}", image)
        print(render_markdown(snapshot.payload))

    def run(self, ignore_schedule: bool = False) -> None:
        """Post the weekly report once, with an optional schedule bypass."""
        config = Config.load()
        now = datetime.now(config.timezone)
        period = period_for_week(
            current_week_start(now),
            config.report_time,
            config.timezone,
        )
        if not ignore_schedule and not is_post_window(now, period.end):
            raise RuntimeError(
                f"Posting is allowed only for 10 minutes from {period.end.isoformat()}"
            )
        if now < period.end:
            period = period_for_week(
                period.week_start - timedelta(days=7),
                config.report_time,
                config.timezone,
            )

        with PostState(config.state_path) as state:
            if state.was_posted(period.week_start, config.guild_id, config.channel_id):
                print(f"The {period.week_start.isoformat()} report was already posted.")
                return

            async def action(client: discord.Client) -> PostResult:
                parent = await fetch_parent(client, config)
                existing_id = await find_existing_report(client, parent, period)
                if existing_id is not None:
                    return PostResult(message_id=existing_id, posted=False)
                report = await collect_report(parent, period)
                image = await render_highlights(report.highlights)
                message = await publish_report(parent, report, image)
                return PostResult(message_id=message.id, posted=True)

            result = asyncio.run(run_discord_action(config.token.get_secret_value(), action))
            state.record(
                period.week_start,
                config.guild_id,
                config.channel_id,
                result.message_id,
                result.posted,
            )
            verb = "Posted" if result.posted else "Found"
            print(f"{verb} report message {result.message_id} for {period.week_start.isoformat()}.")


def main() -> None:
    """Run the Fire CLI."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fire.Fire(LeadleboardCli)
