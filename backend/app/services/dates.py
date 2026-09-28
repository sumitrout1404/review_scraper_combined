"""Date helpers. All business dates are in Australia/Sydney."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")


def sydney_today() -> date:
    return datetime.now(SYDNEY).date()


def week_start(d: date) -> date:
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def month_start(d: date) -> date:
    return d.replace(day=1)


def period_start(d: date, granularity: str) -> date:
    return week_start(d) if granularity == "week" else month_start(d)


def next_period(d: date, granularity: str) -> date:
    if granularity == "week":
        return d + timedelta(days=7)
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def iter_periods(start: date, end: date, granularity: str):
    p = period_start(start, granularity)
    while p <= end:
        yield p
        p = next_period(p, granularity)


def previous_window(date_from: date, date_to: date) -> tuple[date, date]:
    """Window of the same length ending the day before date_from."""
    length = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1)
    return prev_to - timedelta(days=length - 1), prev_to


def describe_window(date_from: date, date_to: date, today: date | None = None) -> str:
    """Human phrase for a window, e.g. 'this week', 'last week', 'in the last 30 days'."""
    today = today or sydney_today()
    ws = week_start(today)
    if date_from == ws and date_to >= today:
        return "this week"
    if date_from == ws - timedelta(days=7) and date_to == ws - timedelta(days=1):
        return "last week"
    if date_from == month_start(today) and date_to >= today:
        return "this month"
    n = (date_to - date_from).days + 1
    if date_to >= today and n in (7, 14, 30, 60, 90, 180, 365):
        return f"in the last {n} days"
    return f"between {fmt(date_from)} and {fmt(date_to)}"


def fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"
