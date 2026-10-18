"""Validated score, report, and state data."""

from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class DataModel(BaseModel):
    """Validate data fields and prevent field replacement."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Game(StrEnum):
    """A supported daily game."""

    SIZE_IT_UP = "Size It Up"
    RNGDLE = "RNGdle"
    DARTWORDS = "Dartwords"
    WIKIRNG = "WikiRNG"


class Score(DataModel):
    """One parsed Discord score."""

    user_id: int
    display_name: str
    game: Game
    value: int


class GameStanding(DataModel):
    """One player in a game ranking."""

    score: Score
    rank: int
    points: int


class OverallStanding(DataModel):
    """One player in the overall ranking."""

    display_name: str
    rank: int
    points: int
    values: dict[Game, int | None]


class WeeklyReport(DataModel):
    """Ranked results for a report period."""

    week_start: date
    week_end: date
    games: dict[Game, list[GameStanding]]
    overall: list[OverallStanding]


class ReportingPeriod(DataModel):
    """The dates and query times for a report."""

    week_start: date
    start: AwareDatetime
    end: AwareDatetime

    @property
    def week_end(self) -> date:
        """Return the last report date."""
        return self.end.date()


class EmbedField(DataModel):
    """One Discord embed field."""

    name: str
    value: str
    inline: bool = False


class EmbedPayload(DataModel):
    """The Discord report embed."""

    type: Literal["rich"] = "rich"
    color: int = 0xF1C40F
    flags: Literal[0] = 0
    fields: list[EmbedField]


class AttachmentPayload(DataModel):
    """The exact name and text of a report attachment."""

    filename: str
    text: str


class MentionSettings(DataModel):
    """Disable mentions in report messages."""

    parse: list[str] = Field(default_factory=list)


class MessagePayload(DataModel):
    """The content, embed, and attachment sent to Discord."""

    content: str
    embed: EmbedPayload | None = None
    attachment: AttachmentPayload | None = None
    allowed_mentions: MentionSettings = Field(default_factory=MentionSettings)


class PreviewSnapshot(DataModel):
    """A report and its exact Discord payload."""

    schema_version: Literal[1] = 1
    collected_at: AwareDatetime
    guild_id: int
    channel_id: int
    period: ReportingPeriod
    report: WeeklyReport
    payload: MessagePayload


class PostRecord(DataModel):
    """One posted, found, or imported report."""

    week_start: date
    guild_id: int | None = None
    channel_id: int | None = None
    message_id: int | None = None
    recorded_at: AwareDatetime | None = None
    outcome: Literal["posted", "found", "imported"]

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        """Require complete post metadata or an imported date-only record."""
        metadata = (self.guild_id, self.channel_id, self.message_id, self.recorded_at)
        if self.week_start.weekday() != 0:
            raise ValueError("The posted week must start on Monday")
        if self.outcome == "imported":
            if any(value is not None for value in metadata):
                raise ValueError("Imported records must not contain post metadata")
        elif any(value is None for value in metadata):
            raise ValueError("Posted and found records require complete metadata")
        return self


class PostHistory(DataModel):
    """Versioned local post history."""

    schema_version: Literal[1] = 1
    records: list[PostRecord] = Field(default_factory=list)


class PostResult(DataModel):
    """The report message and result of a post attempt."""

    message_id: int
    posted: bool
