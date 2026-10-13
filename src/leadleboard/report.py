"""Render weekly reports for Discord and the terminal."""

from datetime import date

from discord.utils import escape_markdown

from leadleboard.models import Game, WeeklyReport

GAME_EMOJIS = {
    Game.SIZE_IT_UP: "📏",
    Game.RNGDLE: "🎲",
    Game.DARTWORDS: "🎯",
}
RANK_EMOJIS = {1: "🥇", 2: "🥈", 3: "🥉"}


def report_marker(week_start: date, week_end: date) -> str:
    """Return the unique visible marker for a weekly report."""
    dates = f"{week_start:%b %d} - {week_end:%b %d, %Y}"
    return f"## 🏆 Weekly High Scores\n-# {dates}"


def format_value(game: Game, value: int | None) -> str:
    """Format one raw game result."""
    if value is None:
        return "-"
    if game is Game.RNGDLE:
        return f"{value:,} EP"
    if game is Game.DARTWORDS:
        return f"{value} guesses"
    return str(value)


def format_rank(rank: int) -> str:
    """Format a rank as a medal or a numbered place."""
    return RANK_EMOJIS.get(rank, f"**{rank}.**")


def format_points(points: int) -> str:
    """Format a point total with the correct unit."""
    unit = "pt" if points == 1 else "pts"
    return f"{points} {unit}"


def report_sections(
    report: WeeklyReport,
    *,
    markdown: bool = False,
) -> list[tuple[str, list[str]]]:
    """Return titled lines for the overall and game sections."""
    overall_lines: list[str] = []
    for standing in report.overall:
        if not markdown:
            values = " | ".join(
                f"{game.value}: {format_value(game, standing.values[game])}" for game in Game
            )
            overall_lines.append(
                f"{standing.rank}. {standing.display_name} - {format_points(standing.points)} | "
                f"{values}"
            )
            continue
        values = " • ".join(
            f"{GAME_EMOJIS[game]} `{format_value(game, standing.values[game])}`" for game in Game
        )
        overall_lines.append(
            f"{format_rank(standing.rank)} **{escape_markdown(standing.display_name)}** • "
            f"**{format_points(standing.points)}**\n> {values}"
        )
    if not overall_lines:
        overall_lines = ["No qualifying scores."]

    sections = [("🏆 Overall", overall_lines)]
    for game in Game:
        lines = [
            (
                f"{format_rank(standing.rank)} "
                f"**{escape_markdown(standing.score.display_name)}** — "
                f"`{format_value(game, standing.score.value)}` • "
                f"**{format_points(standing.points)}**"
                if markdown
                else (
                    f"{standing.rank}. {standing.score.display_name} - "
                    f"{format_value(game, standing.score.value)} "
                    f"({format_points(standing.points)})"
                )
            )
            for standing in report.games[game]
        ] or ["No qualifying scores."]
        sections.append((f"{GAME_EMOJIS[game]} {game.value}", lines))
    return sections


def render_text(report: WeeklyReport) -> str:
    """Render the full report as plain text."""
    lines = [report_marker(report.week_start, report.week_end)]
    for title, section_lines in report_sections(report):
        lines.extend(("", title, *section_lines))
    return "\n".join(lines)
