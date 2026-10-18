from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import discord
import pytest

from leadleboard.discord_app import publish_report
from leadleboard.models import Game, PreviewSnapshot, ReportingPeriod, Score
from leadleboard.report import build_message_payload, render_text, report_sections, save_preview
from leadleboard.scoring import build_report


def test_empty_report_text_contains_all_sections() -> None:
    report = build_report([], date(2026, 9, 14), date(2026, 9, 20))
    text = render_text(report)

    assert text.startswith("## 🏆 Weekly High Scores\n-# Sep 14 - Sep 20, 2026")
    assert "Overall" in text
    assert all(game.value in text for game in Game)
    assert text.count("No qualifying scores.") == len(Game) + 1


def test_discord_report_escapes_markdown_in_names() -> None:
    report = build_report(
        [Score(user_id=1, display_name="**Ada**", game=Game.SIZE_IT_UP, value=254)],
        date(2026, 9, 14),
        date(2026, 9, 20),
    )

    overall, size_it_up, *_ = report_sections(report, markdown=True)

    assert r"**\*\*Ada\*\***" in overall[1][0]
    assert r"\*\*Ada\*\*" in size_it_up[1][0]
    assert "**Ada**" in report_sections(report)[0][1][0]


def test_discord_report_uses_markdown_and_emojis() -> None:
    report = build_report(
        [Score(user_id=1, display_name="Ada", game=Game.SIZE_IT_UP, value=254)],
        date(2026, 9, 14),
        date(2026, 9, 20),
    )

    sections = report_sections(report, markdown=True)

    assert sections[0][0] == "🏆 Overall"
    assert sections[0][1] == ["🥇 **Ada** · `1 pt`\n-# 📏 254 · 🎲 - · 🎯 - · 📚 -"]
    assert sections[1][0] == "📏 Size It Up"
    assert sections[1][1] == ["🥇 Ada\n-# `254`"]


def test_wikirng_report_uses_sp() -> None:
    report = build_report(
        [Score(user_id=1, display_name="Ada", game=Game.WIKIRNG, value=33647)],
        date(2026, 9, 14),
        date(2026, 9, 20),
    )

    sections = report_sections(report, markdown=True)

    assert "📚 33,647 SP" in sections[0][1][0]
    assert sections[-1] == ("📚 WikiRNG", ["🥇 Ada\n-# `33,647 SP`"])
    assert "33,647 SP" in render_text(report)


@pytest.mark.parametrize("count", [5, 6])
def test_game_fields_show_top_three(count: int) -> None:
    scores = [
        Score(user_id=index, display_name=f"P{index}", game=Game.RNGDLE, value=index)
        for index in range(count)
    ]
    report = build_report(scores, date(2026, 9, 14), date(2026, 9, 20))

    lines = report_sections(report, markdown=True)[2][1]

    assert lines[-1] == f"-# +{count - 3} more"
    assert len(lines) == 4


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
        pieces = [sent["content"]]
        if sent["embed"].description:
            pieces.append(sent["embed"].description)
        for field in sent["embed"].fields:
            if field.name != "\u200b":
                pieces.extend((f"### {field.name}", field.value))
        pieces.append(f"-# {sent['embed'].footer.text}")
        assert (directory / "report.md").read_text() == "\n\n".join([*pieces, *image_link])
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
