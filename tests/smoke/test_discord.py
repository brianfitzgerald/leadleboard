"""Read live test-server data and save exact Discord previews."""

from datetime import UTC, datetime, timedelta

import discord
import pytest

from leadleboard.config import Config
from leadleboard.discord_app import check_access, collect_report, fetch_parent, run_discord_action
from leadleboard.models import Game, PreviewSnapshot, ReportingPeriod, WeeklyReport
from leadleboard.report import build_message_payload, save_preview
from leadleboard.schedule import current_week_start, period_for_week
from tests.smoke_plugin import SmokeRun

pytestmark = pytest.mark.smoke


async def test_access(smoke_config: Config, smoke_run: SmokeRun) -> None:
    async def action(client: discord.Client) -> list[str]:
        return await check_access(client, smoke_config)

    details = await run_discord_action(smoke_config.token.get_secret_value(), action)
    smoke_run.results.access_details.extend(details)
    smoke_run.results.warnings.extend(line for line in details if line.startswith("Warning:"))
    smoke_run.save()
    assert any(line.startswith("Guild:") for line in details)
    assert any(line.startswith("Report channel:") for line in details)


@pytest.mark.parametrize("period_name", ["current-week", "previous-week", "last-90-days"])
async def test_report(smoke_config: Config, smoke_run: SmokeRun, period_name: str) -> None:
    now = datetime.now(smoke_config.timezone)
    if period_name == "last-90-days":
        start = now - timedelta(days=90)
        period = ReportingPeriod(week_start=start.date(), start=start, end=now)
    else:
        week = current_week_start(now)
        if period_name == "previous-week":
            week -= timedelta(days=7)
        period = period_for_week(week, smoke_config.report_time, smoke_config.timezone)
        if period.end > now:
            period = ReportingPeriod(week_start=week, start=period.start, end=now)

    async def action(client: discord.Client) -> WeeklyReport:
        parent = await fetch_parent(client, smoke_config)
        return await collect_report(parent, period)

    report = await run_discord_action(smoke_config.token.get_secret_value(), action)
    snapshot = PreviewSnapshot(
        collected_at=datetime.now(UTC),
        guild_id=smoke_config.guild_id,
        channel_id=smoke_config.channel_id,
        period=period,
        report=report,
        payload=build_message_payload(report),
    )
    files = save_preview(snapshot, smoke_run.directory, period_name)
    smoke_run.results.artifacts.extend(path.name for path in files)
    smoke_run.save()
    assert set(report.games) == set(Game)
    assert report.week_start == period.week_start
    assert report.week_end == period.week_end
    assert PreviewSnapshot.model_validate_json(files[1].read_text()) == snapshot
    if period_name == "last-90-days":
        required_games = (Game.SIZE_IT_UP, Game.RNGDLE, Game.DARTWORDS)
        assert all(report.games[game] for game in required_games), "Expected existing test scores"
