import httpx
import pytest

from dle_bot.parsers import (
    parse_dartwords,
    parse_dartwords_description,
    parse_rngdle,
    parse_size_it_up,
)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            """Size It Up
Overall Score 254

🟥⬜⬜⬜⬜ 28
https://magnitudle.com/size-it-up""",
            254,
        ),
        ("Size It Up\nOverall Score 501\nhttps://magnitudle.com/size-it-up", None),
        ("Overall Score 254", None),
    ],
)
def test_parse_size_it_up(content: str, expected: int | None) -> None:
    assert parse_size_it_up(content) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("RNGdle 🎲 122228\n\n203,506 EP\nhttps://rngdle.com", 203506),
        ("RNGdle\nnot a score\nhttps://rngdle.com", None),
        ("203,506 EP", None),
    ],
)
def test_parse_rngdle(content: str, expected: int | None) -> None:
    assert parse_rngdle(content) == expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("I solved today's Dartwords in 5 guesses!", 5),
        ("I solved today\u2019s Dartwords in 1 guess!", 1),
        ("I did not solve today's Dartwords.", None),
        ("I solved today's Dartwords in 11 guesses!", None),
    ],
)
def test_parse_dartwords_description(description: str, expected: int | None) -> None:
    assert parse_dartwords_description(description) == expected


async def test_parse_dartwords_uses_embed() -> None:
    async with httpx.AsyncClient() as client:
        value = await parse_dartwords(
            "https://www.dartwords.com/share?id=tl7i9vhphy",
            ["I solved today's Dartwords in 5 guesses!"],
            client,
        )
    assert value == 5


async def test_parse_dartwords_fetches_metadata() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=(
                '<meta property="og:description" '
                'content="I solved today\'s Dartwords in 3 guesses!">'
            ),
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        value = await parse_dartwords(
            "[result](https://dartwords.com/share?id=abcd1234&utm_source=copy)",
            [],
            client,
        )
    assert value == 3


@pytest.mark.parametrize(
    "content",
    [
        "https://example.com/share?id=abcd1234",
        "https://dartwords.com/other?id=abcd1234",
        "https://dartwords.com/share?id=bad!",
    ],
)
async def test_parse_dartwords_rejects_invalid_urls(content: str) -> None:
    async with httpx.AsyncClient() as client:
        assert await parse_dartwords(content, [], client) is None


async def test_parse_dartwords_handles_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    async with httpx.AsyncClient(transport=transport) as client:
        value = await parse_dartwords(
            "https://dartwords.com/share?id=abcd1234",
            [],
            client,
        )
    assert value is None
