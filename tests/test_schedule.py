from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from dle_bot.schedule import current_week_start, is_post_window, period_for_week

ZONE = ZoneInfo("America/Chicago")


def test_period_for_week() -> None:
    period = period_for_week(date(2026, 9, 14), time(21), ZONE)
    assert period.start == datetime(2026, 9, 14, 0, 0, tzinfo=ZONE)
    assert period.end == datetime(2026, 9, 20, 21, 0, tzinfo=ZONE)


def test_period_crosses_daylight_saving_boundary() -> None:
    period = period_for_week(date(2026, 10, 26), time(21), ZONE)
    assert period.start.utcoffset() == timedelta(hours=-5)
    assert period.end.utcoffset() == timedelta(hours=-6)


def test_period_requires_monday() -> None:
    with pytest.raises(ValueError, match="Monday"):
        period_for_week(date(2026, 9, 15), time(21), ZONE)


def test_current_week_start() -> None:
    assert current_week_start(datetime(2026, 9, 20, 20, tzinfo=ZONE)) == date(2026, 9, 14)


def test_post_window() -> None:
    scheduled = datetime(2026, 9, 20, 21, 0, tzinfo=ZONE)
    assert is_post_window(scheduled, scheduled)
    assert is_post_window(scheduled + timedelta(minutes=9, seconds=59), scheduled)
    assert not is_post_window(scheduled - timedelta(seconds=1), scheduled)
    assert not is_post_window(scheduled + timedelta(minutes=10), scheduled)
