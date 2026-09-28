"""Current-vs-previous window summary (GET /api/summary)."""

from __future__ import annotations

from typing import Any

from ..deps import Filters
from .catalog import label_for, list_properties, topic_labels, topic_order
from .dates import previous_window
from .stats import daily_rows, stats_for
from .topic_stats import top_complaints_by_property
from .windows import summary_window


def delta(current: float | None, previous: float | None) -> float | None:
    """Rounded difference, or None when either side has no data."""
    return None if current is None or previous is None else round(current - previous, 2)


def build_summary(f: Filters) -> dict[str, Any]:
    """Stats for the window and the same-length window directly before it, overall and per property."""
    d_from, d_to = summary_window(f)
    p_from, p_to = previous_window(d_from, d_to)
    cur_rows = daily_rows(f.properties, d_from, d_to)
    prev_rows = daily_rows(f.properties, p_from, p_to)
    cur, prev = stats_for(cur_rows), stats_for(prev_rows)
    labels = topic_labels()
    top = top_complaints_by_property(f.properties, d_from, d_to, topic_order())

    by_property = []
    for prop in list_properties(f.properties):
        c, pv = stats_for(cur_rows, prop["id"]), stats_for(prev_rows, prop["id"])
        complaint = top.get(prop["id"])
        by_property.append(
            {
                "property_id": prop["id"],
                "name": prop["name"],
                "short_name": prop["short_name"],
                "current": c,
                "previous": pv,
                "delta_avg_score": delta(c["avg_score"], pv["avg_score"]),
                "top_complaint": (
                    {"topic": complaint[0], "label": label_for(labels, complaint[0]), "count": complaint[1]}
                    if complaint
                    else None
                ),
            }
        )
    return {
        "current": {"date_from": d_from.isoformat(), "date_to": d_to.isoformat(), **cur},
        "previous": {"date_from": p_from.isoformat(), "date_to": p_to.isoformat(), **prev},
        "delta_avg_score": delta(cur["avg_score"], prev["avg_score"]),
        "delta_count": cur["count"] - prev["count"],
        "by_property": by_property,
    }
