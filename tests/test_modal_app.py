import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

import deploy.modal_app as deployment
import leadleboard.cards as cards
import leadleboard.cli as cli
import leadleboard.discord_app as discord_app

pytestmark = pytest.mark.filterwarnings(
    "ignore:The weekly_report function is executing locally:UserWarning"
)


@pytest.fixture
def modal_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Use local test settings and a temporary volume file."""
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "1")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "2")
    monkeypatch.setenv("LEADLEBOARD_STATE_PATH", "original-state")
    saved_state = tmp_path / "post-state.json"
    monkeypatch.setattr(deployment, "STATE_PATH", saved_state)
    monkeypatch.setattr(deployment, "volume", Mock())
    return saved_state


@pytest.mark.parametrize("action", ["check", "preview"])
def test_read_only_actions_do_not_access_state(
    monkeypatch: pytest.MonkeyPatch, modal_settings: Path, action: str
) -> None:
    commands = Mock()
    monkeypatch.setattr(cli, "LeadleboardCli", Mock(return_value=commands))

    deployment.weekly_report.local(action=action)

    getattr(commands, action).assert_called_once()
    commands.run.assert_not_called()
    cast(Mock, deployment.volume).reload.assert_not_called()
    cast(Mock, deployment.volume).commit.assert_not_called()
    assert not modal_settings.exists()


@pytest.mark.parametrize("existing", [False, True])
def test_run_copies_state_and_commits_after_success(
    monkeypatch: pytest.MonkeyPatch, modal_settings: Path, existing: bool
) -> None:
    if existing:
        modal_settings.write_text("old state")

    def run() -> None:
        local_state = Path(os.environ["LEADLEBOARD_STATE_PATH"])
        assert local_state != modal_settings
        assert local_state.exists() == existing
        if existing:
            assert local_state.read_text() == "old state"
        local_state.write_text("new state")
        print("Posted report.")

    monkeypatch.setattr(cli.LeadleboardCli, "run", staticmethod(run))

    result = deployment.weekly_report.local()

    assert result == "Posted report.\n"
    assert modal_settings.read_text() == "new state"
    assert os.environ["LEADLEBOARD_STATE_PATH"] == "original-state"
    cast(Mock, deployment.volume).reload.assert_called_once()
    cast(Mock, deployment.volume).commit.assert_called_once()


@pytest.mark.parametrize("previous_path", [None, "original-state"])
def test_failed_run_preserves_saved_state_and_restores_environment(
    monkeypatch: pytest.MonkeyPatch, modal_settings: Path, previous_path: str | None
) -> None:
    if previous_path is None:
        monkeypatch.delenv("LEADLEBOARD_STATE_PATH")
    modal_settings.write_text("old state")
    monkeypatch.setattr(cli.LeadleboardCli, "run", Mock(side_effect=RuntimeError("failed")))

    with pytest.raises(RuntimeError, match="failed"):
        deployment.weekly_report.local()

    assert modal_settings.read_text() == "old state"
    assert os.environ.get("LEADLEBOARD_STATE_PATH") == previous_path
    cast(Mock, deployment.volume).commit.assert_not_called()


def test_test_post_publishes_without_changing_state(
    monkeypatch: pytest.MonkeyPatch, modal_settings: Path
) -> None:
    parent = Mock()
    report = Mock()
    monkeypatch.setattr(discord_app, "fetch_parent", AsyncMock(return_value=parent))
    monkeypatch.setattr(discord_app, "collect_report", AsyncMock(return_value=report))
    publisher = AsyncMock(return_value=Mock(id=123))
    monkeypatch.setattr(discord_app, "publish_report", publisher)
    monkeypatch.setattr(cards, "render_highlights", AsyncMock(return_value=b"png"))

    async def run_action(token: str, action: Callable[[discord.Client], Awaitable[int]]) -> int:
        return await action(Mock())

    monkeypatch.setattr(discord_app, "run_discord_action", run_action)

    result = deployment.weekly_report.local(action="test-post")

    assert "Posted deployment test message 123" in result
    publisher.assert_awaited_once_with(parent, report, b"png")
    cast(Mock, deployment.volume).commit.assert_not_called()
    assert not modal_settings.exists()


def test_invalid_action_is_rejected(modal_settings: Path) -> None:
    with pytest.raises(ValueError, match="Unknown report action"):
        deployment.weekly_report.local(action="invalid")
    cast(Mock, deployment.volume).reload.assert_not_called()
