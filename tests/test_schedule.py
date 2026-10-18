from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from leadleboard.schedule import current_week_start, period_for_week

ZONE = ZoneInfo("America/Chicago")


def test_period_for_week() -> None:
    period = period_for_week(date(2026, 9, 14), time(21), ZONE)
    assert period.start == datetime(2026, 9, 13, 21, 0, tzinfo=ZONE)
    assert period.end == datetime(2026, 9, 20, 21, 0, tzinfo=ZONE)
    assert period.week_start == date(2026, 9, 14)
    assert period.week_end == date(2026, 9, 20)


def test_consecutive_periods_have_no_gap() -> None:
    first = period_for_week(date(2026, 9, 14), time(21), ZONE)
    second = period_for_week(date(2026, 9, 21), time(21), ZONE)
    assert first.end == second.start


def test_period_crosses_daylight_saving_boundary() -> None:
    period = period_for_week(date(2026, 10, 26), time(21), ZONE)
    assert period.start.utcoffset() == timedelta(hours=-5)
    assert period.end.utcoffset() == timedelta(hours=-6)


def test_period_requires_monday() -> None:
    with pytest.raises(ValueError, match="Monday"):
        period_for_week(date(2026, 9, 15), time(21), ZONE)


def test_current_week_start() -> None:
    assert current_week_start(datetime(2026, 9, 20, 20, tzinfo=ZONE)) == date(2026, 9, 14)
