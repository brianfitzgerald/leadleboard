"""Render weekly reports for Discord and the terminal."""

from datetime import date
from pathlib import Path

from discord.utils import escape_markdown

from leadleboard.models import (
    AttachmentPayload,
    EmbedField,
    EmbedFooter,
    EmbedImage,
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
GAME_FIELD_LIMIT = 3


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
        values = " · ".join(
            f"{GAME_EMOJIS[game]} {format_value(game, standing.values[game])}" for game in Game
        )
        overall_lines.append(
            f"{format_rank(standing.rank)} **{escape_markdown(standing.display_name)}** · "
            f"`{format_points(standing.points)}`\n-# {values}"
        )
    if not overall_lines:
        overall_lines = ["No qualifying scores."]

    sections = [("🏆 Overall", overall_lines)]
    for game in Game:
        standings = report.games[game]
        if markdown:
            lines = [
                f"{format_rank(standing.rank)} {escape_markdown(standing.score.display_name)}"
                f"\n-# `{format_value(game, standing.score.value)}`"
                for standing in standings[:GAME_FIELD_LIMIT]
            ]
            if len(standings) > GAME_FIELD_LIMIT:
                lines.append(f"-# +{len(standings) - GAME_FIELD_LIMIT} more")
        else:
            lines = [
                f"{standing.rank}. {standing.score.display_name} - "
                f"{format_value(game, standing.score.value)} "
                f"({format_points(standing.points)})"
                for standing in standings
            ]
        lines = lines or ["No qualifying scores."]
        sections.append((f"{GAME_EMOJIS[game]} {game.value}", lines))
    return sections


def render_text(report: WeeklyReport) -> str:
    """Render the full report as plain text."""
    lines = [report_marker(report.week_start, report.week_end)]
    for title, section_lines in report_sections(report):
        lines.extend(("", title, *section_lines))
    return "\n".join(lines)


def image_filename(report: WeeklyReport) -> str:
    """Return the highlight image file name for a report."""
    return f"highlights-{report.week_start.isoformat()}.png"


def build_message_payload(report: WeeklyReport, image: bool = False) -> MessagePayload:
    """Build the message used by publishing and saved previews."""
    marker = report_marker(report.week_start, report.week_end)
    sections = report_sections(report, markdown=True)
    oversized = any(len(line) > 1000 for _, lines in sections for line in lines)
    description = None
    if report.highlights:
        mvp = report.highlights[0]
        stats = " · ".join(f"{value} {label.lower()}" for value, label in mvp.stats)
        description = f"👑 MVP: **{escape_markdown(mvp.display_name)}** · {stats}"
    players = len(report.overall)
    results = sum(len(standings) for standings in report.games.values())
    footer = EmbedFooter(
        text=f"{players} {'player' if players == 1 else 'players'} · "
        f"{results} best {'result' if results == 1 else 'results'}"
    )
    filename = image_filename(report) if image else None
    fields: list[EmbedField] = []
    total_length = len(marker) + len(description or "") + len(footer.text)
    game_fields = 0
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
        inline = title != sections[0][0]
        for index, chunk in enumerate(chunks):
            field_title = title if index == 0 else f"{title} continued"
            fields.append(EmbedField(name=field_title, value=chunk, inline=inline))
            total_length += len(field_title) + len(chunk)
        if inline:
            game_fields += 1
            # A blank third column keeps game fields two per row.
            if game_fields % 2 == 0:
                fields.append(EmbedField(name="\u200b", value="\u200b", inline=True))
    if not oversized and total_length <= 5800 and len(fields) <= 25:
        return MessagePayload(
            content=marker,
            embed=EmbedPayload(
                description=description,
                fields=fields,
                image=None if filename is None else EmbedImage(url=f"attachment://{filename}"),
                footer=footer,
            ),
            image_filename=filename,
        )
    return MessagePayload(
        content=marker,
        attachment=AttachmentPayload(
            filename=f"high-scores-{report.week_start.isoformat()}.txt",
            text=render_text(report),
        ),
        image_filename=filename,
    )


def render_markdown(payload: MessagePayload) -> str:
    """Copy message content, embed text, and the image link without changing their text."""
    parts = [payload.content]
    if payload.embed is not None:
        if payload.embed.description is not None:
            parts.append(payload.embed.description)
        for field in payload.embed.fields:
            if field.name != "\u200b":
                parts.extend((f"### {field.name}", field.value))
        if payload.embed.footer is not None:
            parts.append(f"-# {payload.embed.footer.text}")
    if payload.image_filename is not None:
        parts.append(f"![Highlights]({payload.image_filename})")
    return "\n\n".join(parts)


def save_preview(
    snapshot: PreviewSnapshot,
    directory: Path,
    name: str,
    image: bytes | None = None,
) -> list[Path]:
    """Save exact message text, report data, the highlight image, and any attachment."""
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / f"{name}.md"
    json_path = directory / f"{name}.json"
    markdown_path.write_text(render_markdown(snapshot.payload), encoding="utf-8")
    json_path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    paths = [markdown_path, json_path]
    if image is not None and snapshot.payload.image_filename is not None:
        image_path = directory / snapshot.payload.image_filename
        image_path.write_bytes(image)
        paths.append(image_path)
    if snapshot.payload.attachment is not None:
        attachment = snapshot.payload.attachment
        attachment_path = directory / attachment.filename
        attachment_markdown = directory / f"{name}-attachment.md"
        attachment_path.write_bytes(attachment.text.encode("utf-8"))
        attachment_markdown.write_bytes(attachment.text.encode("utf-8"))
        paths.extend((attachment_path, attachment_markdown))
    return paths
