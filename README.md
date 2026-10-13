# Leadleboard

Leadleboard reads weekly game results from Discord threads and posts one high score report.

## Scoring

- The report period starts at the previous Sunday report time and ends Sunday at the configured
  report time. A result posted after the Sunday report counts for the next week.
- Each player keeps their best result for each game.
- Higher scores win Size It Up and RNGdle. Fewer guesses win Dartwords.
- With `N` players in a game, ranks receive `N` through `1` points.
- Tied players receive the same competition-rank points. A missing game receives zero points.

## Install

Install the project and development tools:

```sh
uv sync
```

Copy `.env.example` to `.env`. Set the bot token, guild ID, and parent channel ID.
`.env` is ignored by Git. Make the file readable only by your user:

```sh
chmod 600 .env
```

## Add the bot to Discord

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Open the Bot page. Create the bot user if needed, reset its token, and put the token in `.env`.
   Never share or commit the token.
3. Enable Message Content under Privileged Gateway Intents on the Bot page. Turn off Public Bot.
4. Open Installation. Set Install Link to None.
5. Open OAuth2, then URL Generator. Select the `bot` scope. Do not select permissions.
6. Open the generated URL, select the server, and authorize the bot.
7. Open the parent channel settings, then Permissions. Add the bot and allow View Channel,
   Read Message History, Send Messages, Embed Links, and Attach Files. Threads use the
   permissions of the parent channel.
8. On each other category, add the bot and deny View Channel. Do the same for each channel that
   is not synced to a category.
9. Enable Developer Mode in Discord. Copy the server and parent channel IDs into `.env`.
10. Check permissions and read one message from the parent and each public thread:

```sh
uv run leadleboard check
```

Discord has no application setting that limits a bot to one channel. The channel permissions
above set the limit. `check` prints a warning for each other channel the bot can view, each other
server the bot is in, and each bot role that grants more than the five permissions. Correct each
warning, then run `check` again.

The bot scans the parent channel and all active and archived public threads. It detects the
game from each message. Thread names do not affect parsing. The bot sends messages only to the
parent channel. It does not receive message events. It does not need Administrator, Manage
Threads, Create Threads, or Send Messages in Threads.

## Preview

Preview the current week without posting or changing post state:

```sh
uv run leadleboard preview
```

Preview a past week by its Monday date:

```sh
uv run leadleboard preview --week 2026-09-14
```

## Schedule on macOS

`run` posts only during the first ten minutes after the configured Sunday report time. It
uses a locked state file and the Discord report marker to prevent a second weekly post.

To post outside the schedule window, use:

```sh
uv run leadleboard run --ignore-schedule
```

This option posts the last complete week. Before the Sunday report time, that is the previous
week. This option does not bypass the weekly duplicate protection.

Open the current user's crontab:

```sh
crontab -e
```

Add this entry:

```cron
0 21 * * 0 cd /Users/brian/repos/leadleboard && /opt/homebrew/bin/uv run leadleboard run >> /Users/brian/Library/Logs/leadleboard.log 2>&1
```

The cron time must match `LEADLEBOARD_REPORT_TIME`. The Mac timezone must match
`LEADLEBOARD_TIMEZONE`, which defaults to `America/Chicago`. The Mac must be awake at the scheduled time because cron does
not run missed jobs after sleep.

## Development

```sh
uv run pytest
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pre-commit run --all-files
```
