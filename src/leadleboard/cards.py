"""Render sports-style highlight cards as one PNG grid."""

import io
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from leadleboard.models import Highlight

FONT_PATH = Path(__file__).parent / "assets" / "BebasNeue-Regular.ttf"
CARD_SIZE = (600, 750)
GAP = 6


def font(size: int) -> ImageFont.FreeTypeFont:
    """Load the card font at one size."""
    return ImageFont.truetype(FONT_PATH, size)


def shadowed_text(
    card: Image.Image,
    position: tuple[float, float],
    text: str,
    text_font: ImageFont.FreeTypeFont,
    scale: float,
    fill: tuple[int, int, int, int] = (255, 255, 255, 255),
    anchor: str = "mm",
) -> None:
    """Draw text with a soft drop shadow."""
    shadow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text(
        (position[0] + 4 * scale, position[1] + 6 * scale),
        text,
        font=text_font,
        fill=(0, 0, 0, 220),
        anchor=anchor,
    )
    card.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8 * scale)))
    ImageDraw.Draw(card).text(position, text, font=text_font, fill=fill, anchor=anchor)


def fitted_font(text: str, size: int, max_width: int) -> ImageFont.FreeTypeFont:
    """Return the largest font up to size that fits text in max_width."""
    while size > 12 and font(size).getlength(text) > max_width:
        size -= 4
    return font(size)


async def fetch_avatars(highlights: list[Highlight], client: httpx.AsyncClient) -> dict[str, bytes]:
    """Download each avatar once and skip failed downloads."""
    avatars: dict[str, bytes] = {}
    for url in {item.avatar_url for item in highlights if item.avatar_url is not None}:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        avatars[url] = response.content
    return avatars


def render_cards(highlights: list[Highlight], avatars: dict[str, bytes]) -> bytes | None:
    """Render cards two per row, with the first card large on the left for an odd count."""
    if not highlights:
        return None
    lead = len(highlights) % 2 == 1
    tiles = highlights[1:] if lead else highlights
    columns = min(2, len(tiles))
    rows = max(1, -(-len(tiles) // 2))
    grid_height = rows * CARD_SIZE[1] + (rows - 1) * GAP
    images: list[Image.Image] = []
    for index, highlight in enumerate(highlights):
        avatar = avatars.get(highlight.avatar_url) if highlight.avatar_url is not None else None
        scale = grid_height / CARD_SIZE[1] if lead and index == 0 else 1.0
        size = (round(CARD_SIZE[0] * scale), round(CARD_SIZE[1] * scale))
        width, height = size

        def at(value: float, scale: float = scale) -> int:
            """Scale one base layout value."""
            return round(value * scale)

        accent = (
            (highlight.color >> 16) & 0xFF,
            (highlight.color >> 8) & 0xFF,
            highlight.color & 0xFF,
        )
        photo: Image.Image | None = None
        if avatar is not None:
            try:
                photo = Image.open(io.BytesIO(avatar)).convert("RGBA")
            except OSError:
                photo = None
        if photo is None:
            card = Image.new("RGBA", size, (*(int(part * 0.55) for part in accent), 255))
            initials = (
                "".join(part[0] for part in highlight.display_name.split()[:2]).upper() or "?"
            )
            ImageDraw.Draw(card).text(
                (width / 2, height * 0.32),
                initials,
                font=font(at(320)),
                fill=(255, 255, 255, 90),
                anchor="mm",
            )
        else:
            card = ImageOps.fit(photo, size, Image.Resampling.LANCZOS, centering=(0.5, 0.3))

        # Accent glow from the top and a dark fade to the bottom.
        tint = Image.new("RGBA", size, (*accent, 0))
        fade = Image.new("RGBA", size, (0, 0, 0, 0))
        tint_draw = ImageDraw.Draw(tint)
        fade_draw = ImageDraw.Draw(fade)
        for y in range(height):
            top = max(0.0, 1 - y / (height * 0.45))
            bottom = min(1.0, max(0.0, (y - height * 0.3) / (height * 0.45)))
            tint_draw.line([(0, y), (width, y)], fill=(*accent, int(150 * top**2)))
            fade_draw.line([(0, y), (width, y)], fill=(8, 8, 12, int(250 * bottom**1.2)))
        card.alpha_composite(tint)
        card.alpha_composite(fade)

        vignette = Image.new("L", size, 0)
        ImageDraw.Draw(vignette).ellipse(
            (-width * 0.3, -height * 0.2, width * 1.3, height * 1.1), 255
        )
        vignette = ImageOps.invert(vignette.filter(ImageFilter.GaussianBlur(at(80))))
        card = Image.composite(
            Image.new("RGBA", size, (0, 0, 0, 255)),
            card,
            vignette.point(lambda value: int(value * 0.7)),
        )

        draw = ImageDraw.Draw(card)
        title = highlight.title.upper()
        title_font = font(at(44))
        title_width = title_font.getlength(title) + at(40)
        draw.rectangle(
            ((width - title_width) / 2, at(24), (width + title_width) / 2, at(76)),
            fill=(15, 15, 20, 235),
        )
        draw.text((width / 2, at(52)), title, font=title_font, fill=(*accent, 255), anchor="mm")

        name = highlight.display_name.upper()
        shadowed_text(
            card, (width / 2, at(440)), name, fitted_font(name, at(92), width - at(40)), scale
        )
        banner = highlight.subtitle.upper()
        banner_font = font(at(34))
        banner_width = banner_font.getlength(banner) + at(36)
        band = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(band).rectangle(
            ((width - banner_width) / 2, at(488), (width + banner_width) / 2, at(532)),
            fill=(*accent, 210),
        )
        card.alpha_composite(band)
        ImageDraw.Draw(card).text(
            (width / 2, at(511)), banner, font=banner_font, fill=(255, 255, 255, 255), anchor="mm"
        )

        column_width = (width - at(40)) / len(highlight.stats)
        for stat_index, (value, label) in enumerate(highlight.stats):
            center = at(20) + column_width * (stat_index + 0.5)
            value_font = fitted_font(value, at(150), int(column_width) - at(16))
            shadowed_text(card, (center, at(625)), value, value_font, scale)
            shadowed_text(
                card, (center, at(706)), label.upper(), font(at(40)), scale, fill=(*accent, 255)
            )
        ImageDraw.Draw(card).rectangle((0, height - at(8), width, height), fill=(*accent, 255))
        images.append(card.convert("RGB"))
    left = images[0].width + GAP if lead else 0
    width = left + columns * (CARD_SIZE[0] + GAP) - GAP
    grid = Image.new("RGB", (max(width, images[0].width), grid_height), (0, 0, 0))
    if lead:
        grid.paste(images[0], (0, 0))
    for index, image in enumerate(images[1:] if lead else images):
        row, column = divmod(index, 2)
        grid.paste(image, (left + column * (CARD_SIZE[0] + GAP), row * (CARD_SIZE[1] + GAP)))
    output = io.BytesIO()
    grid.save(output, format="PNG", optimize=True)
    return output.getvalue()


async def render_highlights(highlights: list[Highlight]) -> bytes | None:
    """Download avatars and render the highlight grid."""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        return render_cards(highlights, await fetch_avatars(highlights, client))
