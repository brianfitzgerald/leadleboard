import io

import httpx
import pytest
from PIL import Image

from leadleboard.cards import fetch_avatars, render_cards
from leadleboard.models import Highlight


def highlight(avatar_url: str | None) -> Highlight:
    return Highlight(
        title="MVP",
        subtitle="Oct 05 - Oct 11",
        display_name="Ada Lovelace",
        avatar_url=avatar_url,
        color=0xF1C40F,
        stats=[("12", "Pts"), ("203,506", "EP")],
    )


@pytest.mark.parametrize(
    ("count", "size"),
    [
        (0, None),
        (1, (600, 750)),
        (2, (1206, 750)),
        (3, (606 + 1206, 750)),
        (4, (1206, 1506)),
        (5, (round(600 * 1506 / 750) + 6 + 1206, 1506)),
    ],
)
def test_render_cards_grid_size(count: int, size: tuple[int, int] | None) -> None:
    avatar = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 50, 50)).save(avatar, format="PNG")
    highlights = [highlight("a" if index % 2 else None) for index in range(count)]

    png = render_cards(highlights, {"a": avatar.getvalue()})

    if size is None:
        assert png is None
        return
    assert png is not None
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG"
    assert image.size == size


def test_render_cards_ignores_invalid_avatar() -> None:
    assert render_cards([highlight("a")], {"a": b"not an image"}) is not None


async def test_fetch_avatars_skips_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ok.png":
            return httpx.Response(200, content=b"image")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        avatars = await fetch_avatars(
            [highlight("https://cdn.example/ok.png"), highlight("https://cdn.example/no.png")],
            client,
        )

    assert avatars == {"https://cdn.example/ok.png": b"image"}
