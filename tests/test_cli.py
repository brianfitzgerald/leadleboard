from collections.abc import Awaitable, Callable
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import discord
import pytest
from pydantic import SecretStr

import leadleboard.cli as cli
from leadleboard.config import Config
from leadleboard.models import PostHistory, PostResult, PreviewSnapshot, WeeklyReport
from leadleboard.scoring import build_report


class PostedState:
    """Report that the current week was already posted."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> PostedState:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def was_posted(self, week_start: date, guild_id: int, channel_id: int) -> bool:
        return True


@pytest.fixture
def configured_cli(monkeypatch: pytest.MonkeyPatch) -> cli.LeadleboardCli:
    """Provide a CLI with local configuration and state."""
    config = Config(
        token=SecretStr("token"),
        guild_id=1,
        channel_id=2,
        timezone=ZoneInfo("America/Chicago"),
        report_time=time(21),
        state_path=Path("state"),
    )
    monkeypatch.setattr(cli.Config, "load", lambda: config)
    monkeypatch.setattr(cli, "PostState", PostedState)
    return cli.LeadleboardCli()


def set_now(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    """Replace the CLI clock with a fixed time."""
    monkeypatch.setattr(cli, "datetime", Mock(spec=datetime, now=now.astimezone))


@pytest.mark.parametrize(
    ("now", "expected_week"),
    [
        (datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("America/Chicago")), "2026-09-07"),
        (datetime(2026, 9, 20, 20, 59, tzinfo=ZoneInfo("America/Chicago")), "2026-09-07"),
        (datetime(2026, 9, 20, 21, tzinfo=ZoneInfo("America/Chicago")), "2026-09-14"),
        (datetime(2026, 9, 20, 21, 30, tzinfo=ZoneInfo("America/Chicago")), "2026-09-14"),
    ],
)
def test_run_selects_the_last_complete_week(
    configured_cli: cli.LeadleboardCli,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    now: datetime,
    expected_week: str,
) -> None:
    set_now(monkeypatch, now)

    configured_cli.run()

    assert f"The {expected_week} report was already posted." in capsys.readouterr().out


@pytest.mark.parametrize("week", ["2026-09-07", 20260907])
def test_preview_accepts_text_and_integer_weeks(
    configured_cli: cli.LeadleboardCli,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    week: str | int,
) -> None:
    async def run_action(
        token: str, action: Callable[[discord.Client], Awaitable[WeeklyReport]]
    ) -> WeeklyReport:
        return build_report([], date(2026, 9, 7), date(2026, 9, 13))

    set_now(monkeypatch, datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("America/Chicago")))
    monkeypatch.setattr(cli, "run_discord_action", run_action)

    configured_cli.preview(week=week)

    assert "Weekly High Scores" in capsys.readouterr().out


@pytest.mark.parametrize("existing_id", [123, None])
def test_run_records_found_or_posted_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, existing_id: int | None
) -> None:
    config = Config(
        token=SecretStr("token"),
        guild_id=1,
        channel_id=10,
        timezone=ZoneInfo("America/Chicago"),
        report_time=time(21),
        state_path=tmp_path / "post-state.json",
    )
    monkeypatch.setattr(cli.Config, "load", lambda: config)
    set_now(monkeypatch, datetime(2026, 9, 16, 12, tzinfo=config.timezone))
    parent = AsyncMock(spec=discord.TextChannel)
    monkeypatch.setattr(cli, "fetch_parent", AsyncMock(return_value=parent))
    monkeypatch.setattr(cli, "find_existing_report", AsyncMock(return_value=existing_id))
    report = build_report([], date(2026, 9, 7), date(2026, 9, 13))
    collect = AsyncMock(return_value=report)
    publish = AsyncMock(return_value=AsyncMock(id=456))
    monkeypatch.setattr(cli, "collect_report", collect)
    monkeypatch.setattr(cli, "publish_report", publish)

    async def run_action(
        token: str, action: Callable[[discord.Client], Awaitable[PostResult]]
    ) -> PostResult:
        return await action(AsyncMock(spec=discord.Client))

    monkeypatch.setattr(cli, "run_discord_action", run_action)
    app = cli.LeadleboardCli()
    app.run()
    history = PostHistory.model_validate_json(config.state_path.read_text())
    assert len(history.records) == 1
    assert history.records[0].message_id == (existing_id or 456)
    assert history.records[0].outcome == ("found" if existing_id else "posted")
    if existing_id:
        publish.assert_not_awaited()
        collect.assert_not_awaited()
    else:
        publish.assert_awaited_once()
    app.run()
    assert len(PostHistory.model_validate_json(config.state_path.read_text()).records) == 1


def test_cli_preview_saves_files_without_post_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = Config(
        token=SecretStr("token"),
        guild_id=1,
        channel_id=10,
        timezone=ZoneInfo("America/Chicago"),
        report_time=time(21),
        state_path=tmp_path / "post-state.json",
    )
    monkeypatch.setattr(cli.Config, "load", lambda: config)
    set_now(monkeypatch, datetime(2026, 9, 16, 12, tzinfo=config.timezone))
    report = build_report([], date(2026, 9, 14), date(2026, 9, 16))

    async def run_action(
        token: str, action: Callable[[discord.Client], Awaitable[WeeklyReport]]
    ) -> WeeklyReport:
        return report

    monkeypatch.setattr(cli, "run_discord_action", run_action)
    directory = tmp_path / "previews"
    cli.LeadleboardCli().preview(output_dir=str(directory))
    snapshot = PreviewSnapshot.model_validate_json(
        (directory / "high-scores-2026-09-14.json").read_text()
    )
    assert snapshot.report == report
    assert (directory / "high-scores-2026-09-14.md").read_text() == capsys.readouterr().out.rstrip(
        "\n"
    )
    assert not config.state_path.exists()
