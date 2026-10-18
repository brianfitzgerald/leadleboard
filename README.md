# Leadleboard

Leadleboard reads weekly game results from Discord threads and posts one high score report.

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

Print the exact Discord message text and save Markdown, JSON, and the highlight PNG:

```sh
uv run leadleboard preview --output-dir .data/previews
```

The Markdown keeps the message content, embed description, field values, and footer
unchanged in Discord display order. The highlight PNG link follows the message content, and
field names become `###` headings.
Discord embed layout and color are stored in JSON. If Discord needs
a text attachment, the preview saves its exact bytes as `.txt` and `.md` files.
JSON also stores scores, ranks, query times, server and channel IDs, and collection time.
Repeated previews replace files for the same week in the selected directory.

## Schedule on Modal

The current Modal deployment uses Brian Test Server, channel `dle`. It runs Sunday at
21:00 in `America/Chicago`, including daylight saving changes. 

Create a stable v1 Volume named `leadleboard-state-test`. If local post history exists,
upload `.data/post-state.json` as `/post-state.json` before the first deployment.
Do not replace existing remote history on later deployments.

Deploy from the repository root:

```sh
uv run modal deploy deploy/modal_app.py
```

Run read-only checks through the deployed function:

```sh
uv run modal run deploy/modal_app.py --action check
uv run modal run deploy/modal_app.py --action preview
```

These commands call the deployed function; they do not invoke a second report writer.
To send one explicit test post:

```sh
uv run modal run deploy/modal_app.py --action test-post
```

`test-post` sends a real report to the test channel. Each call sends a message, including
retries. It does not change post history. Use it only for deployment verification.
Normal posting retains the state and Discord duplicate checks:

```sh
uv run modal run deploy/modal_app.py --action run
```

The scheduled call uses the same normal posting action. State is copied to temporary local
storage for file locking, then saved to the Volume after a successful call.
Do not run a local posting schedule at the same time as Modal.

Inspect private logs and stop the deployment with:

```sh
uv run modal app logs leadleboard
uv run modal app stop leadleboard
```

## Smoke tests

Run the read-only Discord tests with pytest:

```sh
uv run pytest --run-smoke -m smoke
```

Each run creates `.data/smoke-tests/<UTC timestamp>-<unique ID>/`. It saves `results.md`,
`results.json`, and exact Markdown, JSON, and highlight PNG previews for the current week,
previous week, and last 90 days. Results include access warnings, errors, timing, and captured test output.
Results are written before collection and after each test phase, including failures and
pytest interruptions. A forced process termination can leave the run marked incomplete.

The tests read the configured server and channel from `.env`. They require the known test
scores for all three games in the last 90 days. They do not send Discord messages or change
permissions. Missing configuration fails an explicit smoke run. Normal pytest runs skip
live tests.

Use `--smoke-output-dir <path>` to select a different parent directory. Each invocation still
creates a separate run directory. All files under `.data/` are ignored by Git.

## Development

```sh
uv run pytest
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pre-commit run --all-files
```

`ty` checks all project Python files. Ruff requires parameter and return annotations.
