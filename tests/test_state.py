from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from leadleboard.models import PostHistory
from leadleboard.state import PostState


@pytest.mark.parametrize("posted", [True, False])
def test_post_state_keeps_history_and_scope(tmp_path: Path, posted: bool) -> None:
    path = tmp_path / "post-state.json"
    weeks = [date(2026, 9, 7), date(2026, 9, 14)]
    with PostState(path) as state:
        for week in weeks:
            assert not state.was_posted(week, 1, 10)
            state.record(week, 1, 10, 123, posted)
            state.record(week, 1, 10, 123, posted)
        assert not state.was_posted(weeks[0], 2, 10)
        assert not state.was_posted(weeks[0], 1, 20)
        state.record(weeks[0], 2, 10, 456, posted)
    with PostState(path) as state:
        assert all(state.was_posted(week, 1, 10) for week in weeks)
        assert state.was_posted(weeks[0], 2, 10)
    history = PostHistory.model_validate_json(path.read_text())
    assert len(history.records) == 3
    assert history.records[0].message_id == 123
    assert history.records[0].recorded_at is not None
    assert history.records[0].outcome == ("posted" if posted else "found")


def test_post_state_rejects_a_second_lock(tmp_path: Path) -> None:
    path = tmp_path / "post-state.json"
    with PostState(path) as state:
        state.record(date(2026, 9, 14), 1, 10, 123, True)
        with pytest.raises(RuntimeError, match="Another run"), PostState(path):
            pass


@pytest.mark.parametrize(
    "content", ["", "not a date", "2026-09-07", "[]", '{"schema_version":2}', '{"records":42}']
)
def test_invalid_state_is_preserved_and_lock_is_released(tmp_path: Path, content: str) -> None:
    path = tmp_path / "post-state.json"
    path.write_text(content)
    for _ in range(2):
        with pytest.raises((ValueError, ValidationError)), PostState(path):
            pass
        assert path.read_text() == content


def test_atomic_write_failure_keeps_previous_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "post-state.json"
    with PostState(path) as state:
        state.record(date(2026, 9, 7), 1, 10, 123, True)
        original = path.read_bytes()

        def fail_replace(source: Path, target: Path) -> None:
            raise OSError("write failed")

        monkeypatch.setattr("leadleboard.state.os.replace", fail_replace)
        with pytest.raises(OSError, match="write failed"):
            state.record(date(2026, 9, 14), 1, 10, 456, True)
        assert not state.was_posted(date(2026, 9, 14), 1, 10)
        assert path.read_bytes() == original
    assert sorted(file.name for file in tmp_path.iterdir()) == [
        "post-state.json",
        "post-state.json.lock",
    ]


def test_unlocked_state_rejects_operations(tmp_path: Path) -> None:
    state = PostState(tmp_path / "post-state.json")
    with pytest.raises(RuntimeError, match="not locked"):
        state.was_posted(date(2026, 9, 7), 1, 10)
    with pytest.raises(RuntimeError, match="not locked"):
        state.record(date(2026, 9, 7), 1, 10, 123, True)


def test_existing_imported_record_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "post-state.json"
    path.write_text('{"records": [{"week_start": "2026-09-07", "outcome": "imported"}]}')
    with PostState(path) as state:
        assert state.was_posted(date(2026, 9, 7), 1, 10)
        state.record(date(2026, 9, 14), 1, 10, 123, True)
    history = PostHistory.model_validate_json(path.read_text())
    assert [record.outcome for record in history.records] == ["imported", "posted"]
