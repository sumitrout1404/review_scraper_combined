"""PeriodStats aggregation: Mongo groups by day/property/sentiment, Python does the rest."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from db import REVIEWS

from ..db import aggregate
from .query import SENTIMENT_EXPR, base_match, pct, r2


def _empty_sentiments() -> dict[str, int]:
    return {"positive": 0, "neutral": 0, "negative": 0}


@dataclass
class Acc:
    """Accumulator that produces a contract ``PeriodStats`` dict."""

    count: int = 0
    total: float = 0.0
    sentiments: dict[str, int] = field(default_factory=_empty_sentiments)

    def add(self, sentiment: str, n: int, score_sum: float) -> None:
        self.count += n
        self.total += float(score_sum or 0)
        self.sentiments[sentiment] = self.sentiments.get(sentiment, 0) + n

    @property
    def avg(self) -> float | None:
        return r2(self.total / self.count) if self.count else None

    def stats(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "avg_score": self.avg,
            "positive": self.sentiments["positive"],
            "neutral": self.sentiments["neutral"],
            "negative": self.sentiments["negative"],
            "pct_positive": pct(self.sentiments["positive"], self.count),
            "pct_negative": pct(self.sentiments["negative"], self.count),
        }


def daily_rows(properties: Sequence[str], date_from: date | None, date_to: date | None) -> list[dict[str, Any]]:
    """Rows of {d: review_date, p: property_id, s: sentiment, n: count, total: score sum}."""
    pipeline = [
        {"$match": base_match(properties, date_from, date_to)},
        {
            "$group": {
                "_id": {"d": "$review_date", "p": "$property_id", "s": SENTIMENT_EXPR},
                "n": {"$sum": 1},
                "total": {"$sum": "$score"},
            }
        },
    ]
    return [{**row["_id"], "n": row["n"], "total": row["total"]} for row in aggregate(REVIEWS, pipeline)]


def stats_for(rows: Iterable[dict[str, Any]], property_id: str | None = None) -> dict[str, Any]:
    """PeriodStats over ``rows`` (optionally one property)."""
    acc = Acc()
    for row in rows:
        if property_id is None or row["p"] == property_id:
            acc.add(row["s"], int(row["n"]), row["total"])
    return acc.stats()
