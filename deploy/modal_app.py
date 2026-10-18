"""Run weekly reports on Modal in the Discord test server."""

from pathlib import Path

import modal

app = modal.App("leadleboard")
STATE_PATH = Path("/state/post-state.json")
volume = modal.Volume.from_name("leadleboard-state-test")
image = (
    modal.Image.from_registry("python:3.14-slim")
    .uv_sync(frozen=True, extra_options="--no-dev")
    .add_local_dir("src/leadleboard", "/root/leadleboard")
)


@app.function(
    image=image,
    schedule=modal.Cron("0 21 * * 0", timezone="America/Chicago"),
    secrets=[modal.Secret.from_name("leadleboard-discord-test")],
    volumes={"/state": volume},
    env={"LEADLEBOARD_TIMEZONE": "America/Chicago", "LEADLEBOARD_REPORT_TIME": "21:00"},
    cpu=0.125,
    memory=128,
    min_containers=0,
    buffer_containers=0,
    max_containers=1,
    single_use_containers=True,
    timeout=660,
    retries=modal.Retries(max_retries=1, initial_delay=60),
)
def weekly_report(action: str = "run") -> str:
    """Run one report action using the test-server settings."""
    import asyncio
    import io
    import os
    from contextlib import redirect_stdout
    from datetime import datetime, timedelta
    from tempfile import TemporaryDirectory

    import discord

    from leadleboard.cli import LeadleboardCli
    from leadleboard.config import Config
    from leadleboard.discord_app import (
        collect_report,
        fetch_parent,
        publish_report,
        run_discord_action,
    )
    from leadleboard.schedule import current_week_start, period_for_week

    if action not in {"run", "check", "preview", "test-post"}:
        raise ValueError(f"Unknown report action: {action}")

    config = Config.load()
    now = datetime.now(config.timezone)
    week = current_week_start(now)
    if now < period_for_week(week, config.report_time, config.timezone).end:
        week -= timedelta(days=7)

    output = io.StringIO()
    with redirect_stdout(output):
        if action == "check":
            LeadleboardCli().check()
        elif action == "preview":
            LeadleboardCli().preview(week=week.isoformat())
        elif action == "test-post":
            period = period_for_week(week, config.report_time, config.timezone)

            async def post(client: discord.Client) -> int:
                parent = await fetch_parent(client, config)
                message = await publish_report(parent, await collect_report(parent, period))
                return message.id

            message_id = asyncio.run(run_discord_action(config.token.get_secret_value(), post))
            print(f"Posted deployment test message {message_id} for {week.isoformat()}.")
        else:
            volume.reload()
            saved_state = STATE_PATH
            previous_path = os.environ.get("LEADLEBOARD_STATE_PATH")
            try:
                with TemporaryDirectory() as directory:
                    local_state = Path(directory) / "post-state.json"
                    if saved_state.exists():
                        local_state.write_bytes(saved_state.read_bytes())
                    os.environ["LEADLEBOARD_STATE_PATH"] = str(local_state)
                    LeadleboardCli().run(ignore_schedule=True)
                    saved_state.write_bytes(local_state.read_bytes())
                    volume.commit()
            finally:
                if previous_path is None:
                    os.environ.pop("LEADLEBOARD_STATE_PATH", None)
                else:
                    os.environ["LEADLEBOARD_STATE_PATH"] = previous_path
    result = output.getvalue()
    print(result, end="")
    return result


@app.local_entrypoint()
def main(action: str = "check") -> None:
    """Call the deployed function without creating another writer."""
    function = modal.Function.from_name("leadleboard", "weekly_report")
    print(function.remote(action=action), end="")
