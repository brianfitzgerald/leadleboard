from datetime import date

from leadleboard.models import Game, Score
from leadleboard.scoring import build_report


def test_highlights_cover_mvp_and_each_game_leader() -> None:
    scores = [
        Score(user_id=1, display_name="Ada", game=Game.SIZE_IT_UP, value=254, avatar_url="a"),
        Score(user_id=2, display_name="Bob", game=Game.SIZE_IT_UP, value=100),
        Score(user_id=1, display_name="Ada", game=Game.DARTWORDS, value=6, avatar_url="a"),
        Score(user_id=2, display_name="Bob", game=Game.DARTWORDS, value=3),
        Score(user_id=1, display_name="Ada", game=Game.RNGDLE, value=203506, avatar_url="a"),
    ]

    report = build_report(scores, date(2026, 10, 5), date(2026, 10, 11))

    assert [(item.title, item.display_name, item.stats) for item in report.highlights] == [
        ("MVP", "Ada", [("4", "Pts"), ("2", "Wins"), ("3", "Games")]),
        ("Size It Up", "Ada", [("254", "Score"), ("2", "Players")]),
        ("RNGdle", "Ada", [("203,506", "EP"), ("1", "Player")]),
        ("Dartwords", "Bob", [("3", "Guesses"), ("2", "Players")]),
    ]
    assert report.highlights[0].avatar_url == "a"


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
