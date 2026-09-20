from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import dle_bot.cli as cli
from dle_bot.config import Config


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
def configured_cli(monkeypatch: pytest.MonkeyPatch) -> cli.DleBotCli:
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
    return cli.DleBotCli()


def test_run_rejects_time_outside_schedule(configured_cli: cli.DleBotCli) -> None:
    with pytest.raises(RuntimeError, match="Posting is allowed only"):
        configured_cli.run()


def test_run_can_ignore_schedule(
    configured_cli: cli.DleBotCli,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configured_cli.run(ignore_schedule=True)

    assert "report was already posted" in capsys.readouterr().out
