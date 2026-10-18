from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr, ValidationError

from leadleboard.config import Config
from leadleboard.models import Game, PostRecord, Score, WeeklyReport
from leadleboard.scoring import build_report


def test_report_json_round_trip() -> None:
    score = Score(user_id=1, display_name="Ada", game=Game.RNGDLE, value=203506)
    report = build_report([score], date(2026, 9, 14), date(2026, 9, 20))
    assert WeeklyReport.model_validate_json(report.model_dump_json()) == report
    with pytest.raises(ValidationError):
        score.__setattr__("value", 42)


@pytest.mark.parametrize(
    "data",
    [
        {"user_id": 1, "display_name": "Ada", "game": "unknown", "value": 1},
        {"user_id": "invalid", "display_name": "Ada", "game": "RNGdle", "value": 1},
        {"user_id": 1, "display_name": "Ada", "game": "RNGdle", "value": 1, "extra": 1},
    ],
)
def test_score_validation(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Score.model_validate(data)


def test_config_does_not_export_token() -> None:
    config = Config(
        token=SecretStr("test-secret"),
        guild_id=1,
        channel_id=10,
        timezone=ZoneInfo("America/Chicago"),
        report_time=time(21),
        state_path=Path(".data/post-state.json"),
    )
    assert "token" not in config.model_dump()
    assert "test-secret" not in config.model_dump_json()
    assert "test-secret" not in repr(config)
    assert config.model_dump(mode="json")["timezone"] == "America/Chicago"


@pytest.mark.parametrize(
    "data",
    [
        {"week_start": "2026-09-14", "outcome": "posted"},
        {"week_start": "2026-09-14", "outcome": "imported", "message_id": 123},
        {"week_start": "2026-09-15", "outcome": "imported"},
    ],
)
def test_post_record_rejects_incomplete_or_invalid_metadata(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PostRecord.model_validate(data)
