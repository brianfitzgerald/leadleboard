"""Calculate preview and scheduled report periods."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class ReportingPeriod:
    """A Monday-to-Sunday Discord history range."""

    start: datetime
    end: datetime

    @property
    def week_start(self) -> date:
        """Return the Monday date."""
        return self.start.date()

    @property
    def week_end(self) -> date:
        """Return the Sunday date."""
        return self.end.date()


def period_for_week(
    week_start: date,
    report_time: time,
    zone: ZoneInfo,
) -> ReportingPeriod:
    """Build a complete report period from a Monday date."""
    if week_start.weekday() != 0:
        raise ValueError("The week date must be a Monday")
    start = datetime.combine(week_start, datetime.min.time(), tzinfo=zone)
    end = datetime.combine(
        week_start + timedelta(days=6),
        report_time,
        tzinfo=zone,
    )
    return ReportingPeriod(start=start, end=end)


def current_week_start(now: datetime) -> date:
    """Return Monday for the supplied local time."""
    return now.date() - timedelta(days=now.weekday())


def is_post_window(now: datetime, scheduled_at: datetime) -> bool:
    """Allow posts during the first ten minutes after the schedule."""
    return scheduled_at <= now < scheduled_at + timedelta(minutes=10)
