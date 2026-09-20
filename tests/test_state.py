from datetime import date

from dle_bot.state import PostState


def test_post_state_records_each_week_once(tmp_path) -> None:
    path = tmp_path / "post-state"
    week = date(2026, 9, 14)

    with PostState(path) as state:
        assert not state.was_posted(week)
        state.record(week)

    with PostState(path) as state:
        assert state.was_posted(week)

    assert path.read_text() == "2026-09-14"
