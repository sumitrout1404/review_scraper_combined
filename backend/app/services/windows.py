"""Resolve default date windows for the endpoints."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException

from db import REVIEWS

from ..db import ro
from ..deps import Filters
from .dates import add_months, iter_periods, month_start, period_start, sydney_today, week_start

MAX_PERIODS = 600
DEFAULT_WEEKS = 26
DEFAULT_MONTHS = 12


def summary_window(f: Filters, today: date | None = None) -> tuple[date, date]:
    """Default is the current Sydney week to date (Monday -> today)."""
    today = today or sydney_today()
    if f.date_from and f.date_to:
        return f.date_from, f.date_to
    if f.date_from:
        return f.date_from, max(f.date_from, today)
    if f.date_to:
        return week_start(f.date_to), f.date_to
    return week_start(today), today


def trend_window(f: Filters, granularity: str, today: date | None = None) -> tuple[date, date]:
    """Default: the last 26 weeks / 12 months, trimmed so it doesn't start before the first review."""
    today = today or sydney_today()
    date_to = f.date_to or max(today, f.date_from or today)
    if f.date_from:
        date_from = f.date_from
    else:
        if granularity == "week":
            date_from = week_start(date_to) - timedelta(weeks=DEFAULT_WEEKS - 1)
        else:
            date_from = add_months(month_start(date_to), -(DEFAULT_MONTHS - 1))
        oldest = ro(REVIEWS).find_one({}, {"review_date": 1}, sort=[("review_date", 1)])
        if oldest and oldest.get("review_date"):
            first = period_start(date.fromisoformat(oldest["review_date"]), granularity)
            if date_from < first <= date_to:
                date_from = first
    n = sum(1 for _ in iter_periods(date_from, date_to, granularity))
    if n > MAX_PERIODS:
        raise HTTPException(
            status_code=422, detail=f"Date range too long for granularity '{granularity}' (max {MAX_PERIODS} periods)"
        )
    return date_from, date_to
