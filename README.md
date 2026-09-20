# DLE Bot

DLE Bot reads weekly game results from Discord threads and posts one high score report.

## Scoring

- The report period starts Monday at 00:00 and ends Sunday at the configured report time.
- Each player keeps their best result for each game.
- Higher scores win Size It Up and RNGdle. Fewer guesses win Dartwords.
- With `N` players in a game, ranks receive `N` through `1` points.
- Tied players receive the same competition-rank points. A missing game receives zero points.

## Install

Install the project and development tools:

```sh
uv sync
```

Copy `.env.example` to `.env`. Set the bot token, guild ID, parent channel ID, and three
thread IDs. `.env` is ignored by Git.

## Add the bot to Discord

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Open the Bot page. Create the bot user if needed, reset its token, and put the token in `.env`.
   Never share or commit the token.
3. Enable Message Content under Privileged Gateway Intents on the Bot page.
4. Open OAuth2, then URL Generator. Select the `bot` scope.
5. Select View Channels, Read Message History, Send Messages, Embed Links, and Attach Files.
6. Open the generated URL, select the server, and authorize the bot.
7. Confirm that the bot role has the same five permissions in the parent channel settings.
8. Enable Developer Mode in Discord. Copy the server, parent channel, and thread IDs into `.env`.
9. Check permissions and read one message from every public active and archived thread:

```sh
uv run dle-bot check
```

The configured game threads must be public threads under the configured parent channel. The bot
does not need Administrator, Manage Threads, Create Threads, or Send Messages in Threads.

## Preview

Preview the current week without posting or changing post state:

```sh
uv run dle-bot preview
```

Preview a past week by its Monday date:

```sh
uv run dle-bot preview --week 2026-09-14
```

## Schedule on macOS

`run` posts only during the first ten minutes after the configured Sunday report time. It
uses a locked state file and the Discord report marker to prevent a second weekly post.

Open the current user's crontab:

```sh
crontab -e
```

Add this entry:

```cron
0 21 * * 0 cd /Users/brian/repos/dle-bot && /opt/homebrew/bin/uv run dle-bot run >> /Users/brian/Library/Logs/dle-bot.log 2>&1
```

The cron time must match `DLE_REPORT_TIME`. The Mac timezone must match `DLE_TIMEZONE`, which
defaults to `America/Chicago`. The Mac must be awake at the scheduled time because cron does
not run missed jobs after sleep.

## Development

```sh
uv run pytest
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pre-commit run --all-files
```
