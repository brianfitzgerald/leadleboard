"""Shared score and report models."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Game(StrEnum):
    """A supported daily game."""

    SIZE_IT_UP = "Size It Up"
    RNGDLE = "RNGdle"
    DARTWORDS = "Dartwords"


@dataclass(frozen=True, slots=True)
class Score:
    """One parsed Discord score."""

    user_id: int
    display_name: str
    game: Game
    value: int


@dataclass(frozen=True, slots=True)
class GameStanding:
    """One player in a game ranking."""

    score: Score
    rank: int
    points: int


@dataclass(frozen=True, slots=True)
class OverallStanding:
    """One player in the overall ranking."""

    display_name: str
    rank: int
    points: int
    values: dict[Game, int | None]


@dataclass(frozen=True, slots=True)
class WeeklyReport:
    """Ranked results for one reporting week."""

    week_start: date
    week_end: date
    games: dict[Game, list[GameStanding]]
    overall: list[OverallStanding]
