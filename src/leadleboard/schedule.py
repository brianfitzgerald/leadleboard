"""Calculate weekly report periods."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from leadleboard.models import ReportingPeriod


def period_for_week(
    week_start: date,
    report_time: time,
    zone: ZoneInfo,
) -> ReportingPeriod:
    """Build a complete report period from a Monday date."""
    if week_start.weekday() != 0:
        raise ValueError("The week date must be a Monday")
    start = datetime.combine(week_start - timedelta(days=1), report_time, tzinfo=zone)
    end = datetime.combine(week_start + timedelta(days=6), report_time, tzinfo=zone)
    return ReportingPeriod(week_start=week_start, start=start, end=end)


def current_week_start(now: datetime) -> date:
    """Return Monday for the supplied local time."""
    return now.date() - timedelta(days=now.weekday())


def last_complete_period(now: datetime, report_time: time, zone: ZoneInfo) -> ReportingPeriod:
    """Return the last weekly period that ended by the supplied time."""
    week = current_week_start(now)
    period = period_for_week(week, report_time, zone)
    if now < period.end:
        period = period_for_week(week - timedelta(days=7), report_time, zone)
    return period
