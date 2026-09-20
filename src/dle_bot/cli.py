"""Python Fire command-line interface."""

import asyncio
import logging
from datetime import date, datetime

import discord
import fire

from dle_bot.config import Config
from dle_bot.discord_app import (
    check_access,
    collect_report,
    fetch_parent,
    find_existing_report,
    publish_report,
    run_discord_action,
)
from dle_bot.report import render_text
from dle_bot.schedule import ReportingPeriod, current_week_start, is_post_window, period_for_week
from dle_bot.state import PostState


class DleBotCli:
    """Collect and report weekly Discord high scores."""

    def check(self) -> None:
        """Validate permissions and public thread history without posting."""
        config = Config.load()

        async def action(client: discord.Client) -> list[str]:
            return await check_access(client, config)

        for line in asyncio.run(run_discord_action(config.token, action)):
            print(line)
        print("Configuration, permissions, and public thread access are valid.")

    def preview(self, week: str | None = None) -> None:
        """Print a weekly report without posting or changing post state."""
        config = Config.load()
        now = datetime.now(config.timezone)
        week_start = current_week_start(now) if week is None else date.fromisoformat(week)
        period = period_for_week(
            week_start,
            config.report_time,
            config.timezone,
        )
        if period.start > now:
            raise ValueError("The preview week cannot be in the future")
        if period.end > now:
            period = ReportingPeriod(start=period.start, end=now)

        async def action(client: discord.Client) -> str:
            report = await collect_report(client, config, period)
            return render_text(report)

        print(asyncio.run(run_discord_action(config.token, action)))

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

        with PostState(config.state_path) as state:
            if state.was_posted(period.week_start):
                print(f"The {period.week_start.isoformat()} report was already posted.")
                return

            async def action(client: discord.Client) -> tuple[int, bool]:
                report = await collect_report(client, config, period)
                parent = await fetch_parent(client, config)
                existing_id = await find_existing_report(client, parent, report, period)
                if existing_id is not None:
                    return existing_id, False
                message = await publish_report(parent, report)
                return message.id, True

            message_id, posted = asyncio.run(run_discord_action(config.token, action))
            state.record(period.week_start)
            verb = "Posted" if posted else "Found"
            print(f"{verb} report message {message_id} for {period.week_start.isoformat()}.")


def main() -> None:
    """Run the Fire CLI."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fire.Fire(DleBotCli)
