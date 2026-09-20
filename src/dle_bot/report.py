"""Render weekly reports for Discord and the terminal."""

from dle_bot.models import Game, WeeklyReport


def report_marker(report: WeeklyReport) -> str:
    """Return the unique visible marker for a weekly report."""
    return f"Weekly High Scores | {report.week_start.isoformat()} to {report.week_end.isoformat()}"


def format_value(game: Game, value: int | None) -> str:
    """Format one raw game result."""
    if value is None:
        return "-"
    if game is Game.RNGDLE:
        return f"{value:,} EP"
    if game is Game.DARTWORDS:
        return f"{value} guesses"
    return str(value)


def report_sections(report: WeeklyReport) -> list[tuple[str, list[str]]]:
    """Return titled lines for the overall and game sections."""
    overall_lines = [
        (
            f"{standing.rank}. {standing.display_name} - {standing.points} pts | "
            + " | ".join(
                f"{game.value}: {format_value(game, standing.values[game])}" for game in Game
            )
        )
        for standing in report.overall
    ] or ["No qualifying scores."]

    sections = [("Overall", overall_lines)]
    for game in Game:
        lines = [
            (
                f"{standing.rank}. {standing.score.display_name} - "
                f"{format_value(game, standing.score.value)} ({standing.points} pts)"
            )
            for standing in report.games[game]
        ] or ["No qualifying scores."]
        sections.append((game.value, lines))
    return sections


def render_text(report: WeeklyReport) -> str:
    """Render the full report as plain text."""
    lines = [report_marker(report)]
    for title, section_lines in report_sections(report):
        lines.extend(("", title, *section_lines))
    return "\n".join(lines)
