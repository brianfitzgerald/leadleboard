from datetime import date

from dle_bot.models import Game
from dle_bot.report import render_text
from dle_bot.scoring import build_report


def test_empty_report_text_contains_all_sections() -> None:
    report = build_report([], date(2026, 9, 14), date(2026, 9, 20))
    text = render_text(report)

    assert text.startswith("Weekly High Scores | 2026-09-14 to 2026-09-20")
    assert "Overall" in text
    assert all(game.value in text for game in Game)
    assert text.count("No qualifying scores.") == 4
