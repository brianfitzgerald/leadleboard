from datetime import date

from dle_bot.models import Game, Score
from dle_bot.report import render_text, report_sections
from dle_bot.scoring import build_report


def test_empty_report_text_contains_all_sections() -> None:
    report = build_report([], date(2026, 9, 14), date(2026, 9, 20))
    text = render_text(report)

    assert text.startswith("## 🏆 Weekly High Scores\n-# Sep 14 - Sep 20, 2026")
    assert "Overall" in text
    assert all(game.value in text for game in Game)
    assert text.count("No qualifying scores.") == 4


def test_discord_report_uses_markdown_and_emojis() -> None:
    report = build_report(
        [Score(1, "Ada", Game.SIZE_IT_UP, 254)],
        date(2026, 9, 14),
        date(2026, 9, 20),
    )

    sections = report_sections(report, markdown=True)

    assert sections[0][0] == "🏆 Overall"
    assert sections[0][1] == ["🥇 **Ada** • **1 pt**\n> 📏 `254` • 🎲 `-` • 🎯 `-`"]
    assert sections[1][0] == "📏 Size It Up"
    assert sections[1][1] == ["🥇 **Ada** — `254` • **1 pt**"]
