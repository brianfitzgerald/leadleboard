"""Select weekly results and calculate rankings."""

from collections import defaultdict
from datetime import date

from leadleboard.models import (
    Game,
    GameStanding,
    Highlight,
    OverallStanding,
    Score,
    WeeklyReport,
)

GAME_COLORS = {
    Game.SIZE_IT_UP: 0x3498DB,
    Game.RNGDLE: 0x9B59B6,
    Game.DARTWORDS: 0xE74C3C,
    Game.WIKIRNG: 0x2ECC71,
}
GAME_LABELS = {
    Game.SIZE_IT_UP: ("High score", "Score", "Score"),
    Game.RNGDLE: ("High score", "EP", "EP"),
    Game.DARTWORDS: ("Fewest guesses", "Guess", "Guesses"),
    Game.WIKIRNG: ("High score", "SP", "SP"),
}


def build_report(scores: list[Score], week_start: date, week_end: date) -> WeeklyReport:
    """Build game and overall rankings from parsed scores."""
    by_game_user: dict[Game, dict[int, list[Score]]] = defaultdict(lambda: defaultdict(list))
    names: dict[int, str] = {}
    avatars: dict[int, str | None] = {}
    for score in scores:
        by_game_user[score.game][score.user_id].append(score)
        names[score.user_id] = score.display_name
        avatars[score.user_id] = score.avatar_url

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
                user_id=user_id,
                display_name=names[user_id],
                rank=rank,
                points=points,
                values=values[user_id],
            )
        )
        previous_points = points
        previous_rank = rank

    def stat(value: int, singular: str, plural: str) -> tuple[str, str]:
        """Return a formatted value and its label."""
        return f"{value:,}", singular if value == 1 else plural

    highlights: list[Highlight] = []
    if overall:
        mvp = overall[0]
        wins = sum(
            standing.score.user_id == mvp.user_id and standing.rank == 1
            for standings in game_results.values()
            for standing in standings
        )
        played = sum(value is not None for value in mvp.values.values())
        highlights.append(
            Highlight(
                title="MVP",
                subtitle=f"{week_start:%b %d} - {week_end:%b %d}",
                display_name=mvp.display_name,
                avatar_url=avatars[mvp.user_id],
                color=0xF1C40F,
                stats=[
                    stat(mvp.points, "Pt", "Pts"),
                    stat(wins, "Win", "Wins"),
                    stat(played, "Game", "Games"),
                ],
            )
        )
    for game, standings in game_results.items():
        if not standings:
            continue
        leader = standings[0].score
        subtitle, singular, plural = GAME_LABELS[game]
        tied = sum(standing.rank == 1 for standing in standings)
        highlights.append(
            Highlight(
                title=game.value,
                subtitle=f"{subtitle} · {tied}-way tie" if tied > 1 else subtitle,
                display_name=leader.display_name,
                avatar_url=avatars[leader.user_id],
                color=GAME_COLORS[game],
                stats=[
                    stat(leader.value, singular, plural),
                    stat(len(standings), "Player", "Players"),
                ],
            )
        )

    return WeeklyReport(
        week_start=week_start,
        week_end=week_end,
        games=game_results,
        overall=overall,
        highlights=highlights,
    )
