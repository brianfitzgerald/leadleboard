import httpx
import pytest

from leadleboard.parsers import (
    parse_dartwords,
    parse_dartwords_description,
    parse_rngdle,
    parse_size_it_up,
    parse_wikirng,
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
        ("Size It Up\nOverall Score 254.5\nhttps://magnitudle.com/size-it-up", None),
        ("Size It Up\nOverall Score 254,000\nhttps://magnitudle.com/size-it-up", None),
        ("Size It Up\nOverall Score 2540\nhttps://magnitudle.com/size-it-up", None),
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
        ("RNGdle\n1,,234 EP\nhttps://rngdle.com", None),
        ("RNGdle\n12,34 EP\nhttps://rngdle.com", None),
        ("RNGdle\n123, EP\nhttps://rngdle.com", None),
        ("RNGdle\n203506 EP\nhttps://rngdle.com", 203506),
        ("RNGdle\n999,999,999 EP\nhttps://rngdle.com", 999_999_999),
        ("RNGdle\n1,000,000,000 EP\nhttps://rngdle.com", None),
        (f"RNGdle\n{'9' * 1500} EP\nhttps://rngdle.com", None),
    ],
)
def test_parse_rngdle(content: str, expected: int | None) -> None:
    assert parse_rngdle(content) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            "WikiRNG 🎲 Juybadam\n\n⬜ BASIC • Bottom 40%\n\n"
            "🟦 🏘️ Tiny Town\n🟩 🎖️ .mil\n🟩 🛖 Village\n+18 more\n\n"
            "33,647 SP\nhttps://wikirng.com/",
            33647,
        ),
        ("WikiRNG\n33647 SP\nhttps://wikirng.com/", 33647),
        ("wikirng\n0 sp\nhttps://wikirng.com/", 0),
        ("WikiRNG\n1,234,567 SP\nhttps://wikirng.com/", 1234567),
        ("33,647 SP", None),
        ("WikiRNG\n33,647 SP", None),
        ("WikiRNG\nBottom 40%\nhttps://wikirng.com/", None),
        ("WikiRNG\n33,647 EP\nhttps://wikirng.com/", None),
        ("WikiRNG\n-33,647 SP\nhttps://wikirng.com/", None),
        ("WikiRNG\n33,64 SP\nhttps://wikirng.com/", None),
        ("WikiRNG\n33.5 SP\nhttps://wikirng.com/", None),
        (f"WikiRNG\n{'9' * 1500} SP\nhttps://wikirng.com/", None),
    ],
)
def test_parse_wikirng(content: str, expected: int | None) -> None:
    assert parse_wikirng(content) == expected


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
