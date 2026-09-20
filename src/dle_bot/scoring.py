"""Select weekly results and calculate rankings."""

from collections import defaultdict
from datetime import date

from dle_bot.models import Game, GameStanding, OverallStanding, Score, WeeklyReport


def build_report(scores: list[Score], week_start: date, week_end: date) -> WeeklyReport:
    """Build game and overall rankings from parsed scores."""
    by_game_user: dict[Game, dict[int, list[Score]]] = defaultdict(lambda: defaultdict(list))
    names: dict[int, str] = {}
    for score in scores:
        by_game_user[score.game][score.user_id].append(score)
        names[score.user_id] = score.display_name

    game_results: dict[Game, list[GameStanding]] = {}
    point_totals: dict[int, int] = defaultdict(int)
    values: dict[int, dict[Game, int | None]] = defaultdict(lambda: {game: None for game in Game})

    for game in Game:
        best_scores: list[Score] = []
        for user_scores in by_game_user[game].values():
            best_scores.append(
                min(user_scores, key=lambda score: score.value)
                if game is Game.DARTWORDS
                else max(user_scores, key=lambda score: score.value)
            )
        best_scores.sort(
            key=lambda score: (
                score.value if game is Game.DARTWORDS else -score.value,
                score.display_name.casefold(),
            )
        )

        standings: list[GameStanding] = []
        previous_value: int | None = None
        previous_rank = 0
        player_count = len(best_scores)
        for index, score in enumerate(best_scores, start=1):
            rank = previous_rank if score.value == previous_value else index
            points = player_count - rank + 1
            standings.append(GameStanding(score=score, rank=rank, points=points))
            point_totals[score.user_id] += points
            values[score.user_id][game] = score.value
            previous_value = score.value
            previous_rank = rank
        game_results[game] = standings

    overall: list[OverallStanding] = []
    sorted_users = sorted(
        point_totals,
        key=lambda user_id: (-point_totals[user_id], names[user_id].casefold()),
    )
    previous_points: int | None = None
    previous_rank = 0
    for index, user_id in enumerate(sorted_users, start=1):
        points = point_totals[user_id]
        rank = previous_rank if points == previous_points else index
        overall.append(
            OverallStanding(
                display_name=names[user_id],
                rank=rank,
                points=points,
                values=values[user_id],
            )
        )
        previous_points = points
        previous_rank = rank

    return WeeklyReport(
        week_start=week_start,
        week_end=week_end,
        games=game_results,
        overall=overall,
    )
