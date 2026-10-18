from datetime import date

from leadleboard.models import Game, Score
from leadleboard.scoring import build_report


def test_build_report_selects_best_scores_and_awards_rank_points() -> None:
    def score(user_id: int, name: str, game: Game, value: int) -> Score:
        return Score(
            user_id=user_id,
            display_name=name,
            game=game,
            value=value,
        )

    scores = [
        score(1, "Ada", Game.SIZE_IT_UP, 100),
        score(1, "Ada", Game.SIZE_IT_UP, 90),
        score(2, "Bob", Game.SIZE_IT_UP, 100),
        score(1, "Ada", Game.RNGDLE, 200),
        score(2, "Bob", Game.RNGDLE, 100),
        score(3, "Cam", Game.RNGDLE, 300),
        score(1, "Ada", Game.DARTWORDS, 5),
        score(1, "Ada", Game.DARTWORDS, 7),
        score(2, "Bob", Game.DARTWORDS, 3),
    ]

    report = build_report(scores, date(2026, 9, 14), date(2026, 9, 20))

    size = report.games[Game.SIZE_IT_UP]
    assert [(item.score.value, item.rank, item.points) for item in size] == [
        (100, 1, 2),
        (100, 1, 2),
    ]
    rngdle = report.games[Game.RNGDLE]
    assert [(item.score.value, item.rank, item.points) for item in rngdle] == [
        (300, 1, 3),
        (200, 2, 2),
        (100, 3, 1),
    ]
    dartwords = report.games[Game.DARTWORDS]
    assert [(item.score.value, item.rank, item.points) for item in dartwords] == [
        (3, 1, 2),
        (5, 2, 1),
    ]
    assert [(item.display_name, item.rank, item.points) for item in report.overall] == [
        ("Ada", 1, 5),
        ("Bob", 1, 5),
        ("Cam", 3, 3),
    ]


def test_build_empty_report() -> None:
    report = build_report([], date(2026, 9, 14), date(2026, 9, 20))
    assert report.overall == []
    assert all(report.games[game] == [] for game in Game)


def test_wikirng_keeps_highest_score_and_awards_tied_points() -> None:
    scores = [
        Score(user_id=1, display_name="Ada", game=Game.WIKIRNG, value=100),
        Score(user_id=1, display_name="Ada", game=Game.WIKIRNG, value=33647),
        Score(user_id=2, display_name="Bob", game=Game.WIKIRNG, value=33647),
        Score(user_id=3, display_name="Cam", game=Game.WIKIRNG, value=200),
    ]

    report = build_report(scores, date(2026, 9, 14), date(2026, 9, 20))

    assert [(item.score.value, item.rank, item.points) for item in report.games[Game.WIKIRNG]] == [
        (33647, 1, 3),
        (33647, 1, 3),
        (200, 3, 1),
    ]
    assert [(item.display_name, item.points) for item in report.overall] == [
        ("Ada", 3),
        ("Bob", 3),
        ("Cam", 1),
    ]
