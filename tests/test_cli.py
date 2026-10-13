from collections.abc import Awaitable, Callable
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import leadleboard.cli as cli
from leadleboard.config import Config


class PostedState:
    """Report that the current week was already posted."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> PostedState:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def was_posted(self, week_start: object) -> bool:
        return True


@pytest.fixture
def configured_cli(monkeypatch: pytest.MonkeyPatch) -> cli.LeadleboardCli:
    """Provide a CLI with local configuration and state."""
    config = Config(
        token="token",
        guild_id=1,
        channel_id=2,
        timezone=ZoneInfo("America/Chicago"),
        report_time=time(21),
        state_path=Path("state"),
    )
    monkeypatch.setattr(cli.Config, "load", lambda: config)
    monkeypatch.setattr(cli, "PostState", PostedState)
    monkeypatch.setattr(cli, "is_post_window", lambda now, end: False)
    return cli.LeadleboardCli()


def test_run_rejects_time_outside_schedule(configured_cli: cli.LeadleboardCli) -> None:
    with pytest.raises(RuntimeError, match="Posting is allowed only"):
        configured_cli.run()


def test_run_can_ignore_schedule(
    configured_cli: cli.LeadleboardCli,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configured_cli.run(ignore_schedule=True)

    assert "report was already posted" in capsys.readouterr().out


def set_now(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    """Replace the CLI clock with a fixed time."""
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=now.astimezone))


@pytest.mark.parametrize(
    ("now", "expected_week"),
    [
        (datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("America/Chicago")), "2026-09-07"),
        (datetime(2026, 9, 20, 20, 59, tzinfo=ZoneInfo("America/Chicago")), "2026-09-07"),
        (datetime(2026, 9, 20, 21, 30, tzinfo=ZoneInfo("America/Chicago")), "2026-09-14"),
    ],
)
def test_run_ignore_schedule_selects_the_last_complete_week(
    configured_cli: cli.LeadleboardCli,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    now: datetime,
    expected_week: str,
) -> None:
    set_now(monkeypatch, now)

    configured_cli.run(ignore_schedule=True)

    assert f"The {expected_week} report was already posted." in capsys.readouterr().out


@pytest.mark.parametrize("week", ["2026-09-07", 20260907])
def test_preview_accepts_text_and_integer_weeks(
    configured_cli: cli.LeadleboardCli,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    week: str | int,
) -> None:
    async def run_action(token: str, action: Callable[[object], Awaitable[str]]) -> str:
        return "report"

    set_now(monkeypatch, datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("America/Chicago")))
    monkeypatch.setattr(cli, "run_discord_action", run_action)

    configured_cli.preview(week=week)

    assert "report" in capsys.readouterr().out
