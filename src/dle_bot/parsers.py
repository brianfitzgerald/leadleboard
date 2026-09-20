"""Parse game share messages into score values."""

import logging
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import httpx

LOGGER = logging.getLogger(__name__)

SIZE_SCORE_PATTERN = re.compile(r"Overall\s+Score\s+([0-9]{1,3})\b", re.IGNORECASE)
RNGDLE_SCORE_PATTERN = re.compile(r"(?m)^\s*([0-9][0-9,]{0,14})\s+EP\s*$", re.IGNORECASE)
RNGDLE_MAX_SCORE = 999_999_999
DARTWORDS_GUESSES_PATTERN = re.compile(
    r"solved\s+(?:today(?:'s|\u2019s)\s+)?Dartwords\s+in\s+([0-9]{1,2})\s+guess(?:es)?",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"https?://[^\s)>\]]+")
SHARE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{4,64}")


class MetadataParser(HTMLParser):
    """Collect description metadata from an HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.descriptions: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "meta":
            return
        values = {key.casefold(): value for key, value in attrs}
        name = (values.get("name") or values.get("property") or "").casefold()
        content = values.get("content")
        if name in {"description", "og:description", "twitter:description"} and content:
            self.descriptions.append(content)


def parse_size_it_up(content: str) -> int | None:
    """Return a valid Size It Up overall score."""
    if "size it up" not in content.casefold() or "magnitudle.com" not in content.casefold():
        return None
    match = SIZE_SCORE_PATTERN.search(content)
    if match is None:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= 500 else None


def parse_rngdle(content: str) -> int | None:
    """Return a valid RNGdle EP score."""
    if "rngdle" not in content.casefold() or "rngdle.com" not in content.casefold():
        return None
    match = RNGDLE_SCORE_PATTERN.search(content)
    if match is None:
        return None
    value = int(match.group(1).replace(",", ""))
    return value if value <= RNGDLE_MAX_SCORE else None


def parse_dartwords_description(description: str) -> int | None:
    """Return the guess count from Dartwords metadata."""
    match = DARTWORDS_GUESSES_PATTERN.search(description)
    if match is None:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= 10 else None


async def parse_dartwords(
    content: str,
    embed_descriptions: list[str],
    client: httpx.AsyncClient,
) -> int | None:
    """Return Dartwords guesses from an embed or its share page."""
    share_id: str | None = None
    for raw_url in URL_PATTERN.findall(content):
        parsed = urlparse(raw_url.rstrip(".,!?"))
        if parsed.hostname not in {"dartwords.com", "www.dartwords.com"} or parsed.path != "/share":
            continue
        candidate = parse_qs(parsed.query).get("id", [None])[0]
        if candidate and SHARE_ID_PATTERN.fullmatch(candidate):
            share_id = candidate
            break
    if share_id is None:
        return None

    for description in embed_descriptions:
        value = parse_dartwords_description(description)
        if value is not None:
            return value

    try:
        response = await client.get(
            "https://www.dartwords.com/share",
            params={"id": share_id},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        LOGGER.warning("Could not read Dartwords share %s: %s", share_id, error)
        return None

    parser = MetadataParser()
    parser.feed(response.text)
    for description in parser.descriptions:
        value = parse_dartwords_description(description)
        if value is not None:
            return value
    return None
