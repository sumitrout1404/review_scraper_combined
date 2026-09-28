"""Score/sentiment and topic trends, aggregated per day in Mongo and bucketed by week/month in Python."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from db import REVIEWS

from ..db import aggregate
from ..deps import Filters
from .catalog import list_properties, topic_order
from .dates import iter_periods, period_start
from .query import base_match
from .stats import Acc, daily_rows
from .windows import trend_window


def score_trends(f: Filters, granularity: str) -> dict[str, Any]:
    """PeriodStats per period (empty periods included) plus count/avg per property."""
    d_from, d_to = trend_window(f, granularity)
    total: dict[date, Acc] = defaultdict(Acc)
    per_prop: dict[tuple[str, date], Acc] = defaultdict(Acc)
    for row in daily_rows(f.properties, d_from, d_to):
        bucket = period_start(date.fromisoformat(row["d"]), granularity)
        total[bucket].add(row["s"], int(row["n"]), row["total"])
        per_prop[(row["p"], bucket)].add(row["s"], int(row["n"]), row["total"])
    periods = list(iter_periods(d_from, d_to, granularity))
    series = [{"period_start": p.isoformat(), **total.get(p, Acc()).stats()} for p in periods]
    by_property = []
    for prop in list_properties(f.properties):
        points = []
        for p in periods:
            acc = per_prop.get((prop["id"], p), Acc())
            points.append({"period_start": p.isoformat(), "count": acc.count, "avg_score": acc.avg})
        by_property.append({"property_id": prop["id"], "short_name": prop["short_name"], "series": points})
    return {"granularity": granularity, "series": series, "by_property": by_property}


def topic_trends(f: Filters, granularity: str, polarity: str, topics: list[str]) -> dict[str, Any]:
    """Mentions per period per topic, zero-filled for every topic that appears in the range."""
    d_from, d_to = trend_window(f, granularity)
    mention: dict[str, Any] = {"topics.polarity": polarity}
    if topics:
        mention["topics.topic"] = {"$in": topics}
    pipeline = [
        {"$match": base_match(f.properties, d_from, d_to)},
        {"$project": {"review_date": 1, "topics": 1}},
        {"$unwind": "$topics"},
        {"$match": mention},
        {"$group": {"_id": {"r": "$_id", "d": "$review_date", "t": "$topics.topic"}}},
    ]
    counts: dict[tuple[date, str], int] = defaultdict(int)
    for row in aggregate(REVIEWS, pipeline):
        key = row["_id"]
        counts[(period_start(date.fromisoformat(key["d"]), granularity), key["t"])] += 1
    order = topic_order()
    present = sorted({topic for _, topic in counts}, key=lambda k: (order.get(k, len(order)), k))
    series = [
        {"period_start": p.isoformat(), "topic": topic, "mentions": counts.get((p, topic), 0)}
        for p in iter_periods(d_from, d_to, granularity)
        for topic in present
    ]
    return {"series": series}
