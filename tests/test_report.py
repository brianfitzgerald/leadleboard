from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import discord
import pytest

from leadleboard.discord_app import publish_report
from leadleboard.models import Game, PreviewSnapshot, ReportingPeriod, Score
from leadleboard.report import build_message_payload, format_value, render_text, save_preview
from leadleboard.scoring import build_report


def test_empty_report_text_contains_all_sections() -> None:
    report = build_report([], date(2026, 9, 14), date(2026, 9, 20))
    text = render_text(report)

    assert text.startswith("## 🏆 Weekly High Scores\n-# Sep 14 - Sep 20, 2026")
    assert "Overall" in text
    assert all(game.value in text for game in Game)
    assert text.count("No qualifying scores.") == len(Game) + 1


def test_mvp_description_escapes_markdown_in_names() -> None:
    report = build_report(
        [Score(user_id=1, display_name="**Ada**", game=Game.SIZE_IT_UP, value=254)],
        date(2026, 9, 14),
        date(2026, 9, 20),
    )

    embed = build_message_payload(report).embed

    assert embed is not None
    assert embed.description == r"👑 MVP: **\*\*Ada\*\*** · 1 pt · 1 win · 1 game"
    assert "**Ada**" in embed.fields[0].value


def test_embed_tables_show_places_and_leaders() -> None:
    scores = [
        Score(user_id=1, display_name="Ada", game=Game.SIZE_IT_UP, value=254),
        Score(user_id=2, display_name="Bob", game=Game.SIZE_IT_UP, value=100),
        Score(user_id=1, display_name="Ada", game=Game.WIKIRNG, value=33647),
        Score(user_id=2, display_name="Bob", game=Game.DARTWORDS, value=3),
    ]
    report = build_report(scores, date(2026, 9, 14), date(2026, 9, 20))

    embed = build_message_payload(report).embed

    assert embed is not None
    assert [field.name for field in embed.fields] == ["🏆 Standings", "📊 Top scores"]
    assert embed.fields[0].value.splitlines() == [
        "```",
        " #  Player          Pts  Wins",
        "─" * 29,
        " 1  Ada               3     2",
        " 2  Bob               2     1",
        "```",
    ]
    assert embed.fields[1].value.splitlines()[3:6] == [
        "Size  Ada                  254",
        "Dart  Bob                    3",
        "Wiki  Ada            33,647 SP",
    ]
    assert all(len(line) <= 30 for field in embed.fields for line in field.value.splitlines())


@pytest.mark.parametrize(
    ("names", "leader"),
    [
        (["Ada"], "Ada"),
        (["Ada", "Bob", "Cam"], "Ada +2"),
        (["Bartholomew Longname"], "Bartholomew…"),
        (["Bartholomew Longname", "Bob"], "Bartholo… +1"),
        (["Barbara Liskov", "Bob", "Cam", "Dan", "Eve"], "Barbara… +4"),
    ],
)
def test_top_scores_mark_ties_and_cut_names(names: list[str], leader: str) -> None:
    scores = [
        Score(user_id=index, display_name=name, game=Game.RNGDLE, value=10)
        for index, name in enumerate(names)
    ]
    report = build_report(scores, date(2026, 9, 14), date(2026, 9, 20))

    embed = build_message_payload(report).embed

    assert embed is not None
    assert embed.fields[1].value.splitlines()[3].startswith(f"RNG   {leader}")
    assert ("way tie" in report.highlights[1].subtitle) == (len(names) > 1)


def test_long_standings_split_into_code_blocks() -> None:
    scores = [
        Score(user_id=index, display_name=f"Player {index}", game=Game.RNGDLE, value=index)
        for index in range(40)
    ]
    report = build_report(scores, date(2026, 9, 14), date(2026, 9, 20))

    embed = build_message_payload(report).embed

    assert embed is not None
    standings = [field for field in embed.fields if field.name.startswith("🏆 Standings")]
    assert len(standings) > 1
    assert all(
        field.value.startswith("```\n #  Player")
        and field.value.endswith("\n```")
        and len(field.value) <= 1024
        for field in standings
    )
    assert sum(field.value.count("Player ") - 1 for field in standings) == 40


@pytest.mark.parametrize("count", [0, 1, 40, 200])
async def test_saved_preview_matches_publish_payload(tmp_path: Path, count: int) -> None:
    scores = [
        Score(user_id=index, display_name="**Ada**", game=Game.RNGDLE, value=index)
        for index in range(count)
    ]
    report = build_report(scores, date(2026, 9, 14), date(2026, 9, 20))
    period = ReportingPeriod(
        week_start=report.week_start,
        start=datetime(2026, 9, 13, 21, tzinfo=UTC),
        end=datetime(2026, 9, 20, 21, tzinfo=UTC),
    )
    image = b"png" if count else None
    payload = build_message_payload(report, image=image is not None)
    snapshot = PreviewSnapshot(
        collected_at=datetime.now(UTC),
        guild_id=1,
        channel_id=10,
        period=period,
        report=report,
        payload=payload,
    )
    directory = tmp_path / "previews"
    paths = save_preview(snapshot, directory, "report", image)

    channel = AsyncMock(spec=discord.TextChannel)
    await publish_report(channel, report, image)
    sent = channel.send.call_args.kwargs
    assert sent["content"] == payload.content
    image_link = [] if image is None else ["![Highlights](highlights-2026-09-14.png)"]
    if image is not None:
        assert (directory / "highlights-2026-09-14.png").read_bytes() == image
        assert sent["files"][-1].fp.read() == image
    assert [path.name for path in paths][:2] == ["report.md", "report.json"]
    if payload.embed is not None:
        assert sent["embed"].to_dict() == payload.embed.model_dump(exclude_none=True)
        pieces = [sent["content"], *image_link, sent["embed"].description]
        for field in sent["embed"].fields:
            pieces.extend((f"### {field.name}", field.value))
        pieces.append(f"-# {sent['embed'].footer.text}")
        assert (directory / "report.md").read_text() == "\n\n".join(pieces)
    else:
        assert payload.attachment is not None
        content = sent["files"][0].fp.read()
        assert (directory / "report.md").read_text() == "\n\n".join([sent["content"], *image_link])
        assert (directory / payload.attachment.filename).read_bytes() == content
        assert (directory / "report-attachment.md").read_bytes() == content
    assert PreviewSnapshot.model_validate_json((directory / "report.json").read_text()) == snapshot


def test_saved_preview_reports_write_failure(tmp_path: Path) -> None:
    directory = tmp_path / "file"
    directory.write_text("not a directory")
    report = build_report([], date(2026, 9, 14), date(2026, 9, 20))
    snapshot = PreviewSnapshot(
        collected_at=datetime.now(UTC),
        guild_id=1,
        channel_id=10,
        period=ReportingPeriod(
            week_start=report.week_start,
            start=datetime(2026, 9, 13, 21, tzinfo=UTC),
            end=datetime(2026, 9, 20, 21, tzinfo=UTC),
        ),
        report=report,
        payload=build_message_payload(report),
    )
    with pytest.raises(FileExistsError):
        save_preview(snapshot, directory, "report")


@pytest.mark.parametrize("name", ["```Ada", "Ada\nBob", "Ada\tBob"])
def test_player_names_cannot_break_table_rows(name: str) -> None:
    report = build_report(
        [Score(user_id=1, display_name=name, game=Game.RNGDLE, value=10)],
        date(2026, 9, 14),
        date(2026, 9, 20),
    )

    embed = build_message_payload(report).embed

    assert embed is not None
    for field in embed.fields:
        assert len(field.value.splitlines()) == 5
        assert field.value.count("```") == 2
        assert "\t" not in field.value


@pytest.mark.parametrize(("value", "expected"), [(1, "1 guess"), (2, "2 guesses")])
def test_dartwords_guess_label(value: int, expected: str) -> None:
    assert format_value(Game.DARTWORDS, value) == expected
