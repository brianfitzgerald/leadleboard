"""Render weekly reports for Discord and the terminal."""

from datetime import date
from pathlib import Path

from discord.utils import escape_markdown

from leadleboard.models import (
    AttachmentPayload,
    EmbedField,
    EmbedFooter,
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
GAME_SHORT_NAMES = {
    Game.SIZE_IT_UP: "Size",
    Game.RNGDLE: "RNG",
    Game.DARTWORDS: "Dart",
    Game.WIKIRNG: "Wiki",
}
NAME_WIDTH = 14
LEADER_WIDTH = 12


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


def format_points(points: int) -> str:
    """Format a point total with the correct unit."""
    unit = "pt" if points == 1 else "pts"
    return f"{points} {unit}"


def report_sections(report: WeeklyReport) -> list[tuple[str, list[str]]]:
    """Return titled plain-text lines for the overall and game sections."""
    overall_lines = [
        f"{standing.rank}. {standing.display_name} - {format_points(standing.points)} | "
        + " | ".join(f"{game.value}: {format_value(game, standing.values[game])}" for game in Game)
        for standing in report.overall
    ] or ["No qualifying scores."]
    sections = [("🏆 Overall", overall_lines)]
    for game in Game:
        lines = [
            f"{standing.rank}. {standing.score.display_name} - "
            f"{format_value(game, standing.score.value)} ({format_points(standing.points)})"
            for standing in report.games[game]
        ] or ["No qualifying scores."]
        sections.append((f"{GAME_EMOJIS[game]} {game.value}", lines))
    return sections


def fit_name(name: str, width: int = NAME_WIDTH) -> str:
    """Cut a name to a column width."""
    return name if len(name) <= width else name[: width - 1].rstrip() + "…"


def table_chunks(header: str, rows: list[str], limit: int = 1000) -> list[str]:
    """Split table rows into code blocks that each repeat the header."""
    top = f"```\n{header}\n{'─' * len(header)}"
    chunks: list[str] = []
    current = top
    for row in rows:
        if len(current) + len(row) + 5 > limit and current != top:
            chunks.append(f"{current}\n```")
            current = top
        current = f"{current}\n{row}"
    chunks.append(f"{current}\n```")
    return chunks


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
    filename = image_filename(report) if image else None
    description = "No qualifying scores."
    if report.highlights:
        mvp = report.highlights[0]
        stats = " · ".join(f"{value} {label.lower()}" for value, label in mvp.stats)
        description = f"👑 MVP: **{escape_markdown(mvp.display_name)}** · {stats}"

    # Tables stay at 30 characters or less so code blocks do not wrap on phones.
    wins: dict[int, int] = {}
    for standings in report.games.values():
        for standing in standings:
            if standing.rank == 1:
                wins[standing.score.user_id] = wins.get(standing.score.user_id, 0) + 1
    standings_header = f"{'#':>2}  {'Player':<{NAME_WIDTH}}  {'Pts':>3}  {'Wins':>4}"
    standings_rows = [
        f"{standing.rank:>2}  {fit_name(standing.display_name):<{NAME_WIDTH}}  "
        f"{standing.points:>3}  {wins.get(standing.user_id, 0):>4}"
        for standing in report.overall
    ]
    leader_header = f"{'Game':<4}  {'Leader':<{LEADER_WIDTH}}  {'Best':>10}"
    leader_rows: list[str] = []
    for game in Game:
        standings = report.games[game]
        if not standings:
            continue
        ties = sum(standing.rank == 1 for standing in standings) - 1
        suffix = f" +{ties}" if ties else ""
        name = standings[0].score.display_name
        leader = fit_name(name, LEADER_WIDTH - len(suffix)) + suffix
        best = format_value(game, standings[0].score.value).removesuffix(" guesses")
        leader_rows.append(f"{GAME_SHORT_NAMES[game]:<4}  {leader:<{LEADER_WIDTH}}  {best:>10}")

    fields: list[EmbedField] = []
    for title, header, rows in (
        ("🏆 Standings", standings_header, standings_rows),
        ("📊 Top scores", leader_header, leader_rows),
    ):
        if not rows:
            continue
        for index, chunk in enumerate(table_chunks(header, rows)):
            fields.append(
                EmbedField(name=title if index == 0 else f"{title} continued", value=chunk)
            )
    players = len(report.overall)
    results = sum(len(standings) for standings in report.games.values())
    footer = EmbedFooter(
        text=f"{players} {'player' if players == 1 else 'players'} · "
        f"{results} best {'result' if results == 1 else 'results'}"
    )
    total_length = (
        len(marker)
        + len(description)
        + len(footer.text)
        + sum(len(field.name) + len(field.value) for field in fields)
    )
    fits = all(len(field.value) <= 1024 for field in fields)
    if fits and total_length <= 5800 and len(fields) <= 25:
        return MessagePayload(
            content=marker,
            embed=EmbedPayload(description=description, fields=fields, footer=footer),
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
    """Copy message content, the image link, and embed text in Discord display order."""
    parts = [payload.content]
    if payload.image_filename is not None:
        parts.append(f"![Highlights]({payload.image_filename})")
    if payload.embed is not None:
        if payload.embed.description is not None:
            parts.append(payload.embed.description)
        for field in payload.embed.fields:
            parts.extend((f"### {field.name}", field.value))
        if payload.embed.footer is not None:
            parts.append(f"-# {payload.embed.footer.text}")
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
