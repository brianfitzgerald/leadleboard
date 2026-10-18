"""Render weekly reports for Discord and the terminal."""

from datetime import date
from pathlib import Path

from discord.utils import escape_markdown

from leadleboard.models import (
    AttachmentPayload,
    EmbedField,
    EmbedPayload,
    Game,
    MessagePayload,
    PreviewSnapshot,
    WeeklyReport,
)

GAME_EMOJIS = {
    Game.SIZE_IT_UP: "📏",
    Game.RNGDLE: "🎲",
    Game.DARTWORDS: "🎯",
    Game.WIKIRNG: "📚",
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
    if game is Game.WIKIRNG:
        return f"{value:,} SP"
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


def build_message_payload(report: WeeklyReport) -> MessagePayload:
    """Build the message used by publishing and saved previews."""
    marker = report_marker(report.week_start, report.week_end)
    sections = report_sections(report, markdown=True)
    oversized = any(len(line) > 1000 for _, lines in sections for line in lines)
    fields: list[EmbedField] = []
    total_length = len(marker)
    for title, lines in sections:
        chunks: list[str] = []
        current = ""
        for line in lines:
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > 1000:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)
        for index, chunk in enumerate(chunks):
            field_title = title if index == 0 else f"{title} continued"
            fields.append(EmbedField(name=field_title, value=chunk))
            total_length += len(field_title) + len(chunk)
    if not oversized and total_length <= 5800 and len(fields) <= 25:
        return MessagePayload(content=marker, embed=EmbedPayload(fields=fields))
    return MessagePayload(
        content=marker,
        attachment=AttachmentPayload(
            filename=f"high-scores-{report.week_start.isoformat()}.txt",
            text=render_text(report),
        ),
    )


def render_markdown(payload: MessagePayload) -> str:
    """Copy message content and embed fields without changing their text."""
    parts = [payload.content]
    if payload.embed is not None:
        for field in payload.embed.fields:
            parts.extend((field.name, field.value))
    return "\n\n".join(parts)


def save_preview(snapshot: PreviewSnapshot, directory: Path, name: str) -> list[Path]:
    """Save exact message text, report data, and any attachment."""
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / f"{name}.md"
    json_path = directory / f"{name}.json"
    markdown_path.write_text(render_markdown(snapshot.payload), encoding="utf-8")
    json_path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    paths = [markdown_path, json_path]
    if snapshot.payload.attachment is not None:
        attachment = snapshot.payload.attachment
        attachment_path = directory / attachment.filename
        attachment_markdown = directory / f"{name}-attachment.md"
        attachment_path.write_bytes(attachment.text.encode("utf-8"))
        attachment_markdown.write_bytes(attachment.text.encode("utf-8"))
        paths.extend((attachment_path, attachment_markdown))
    return paths
