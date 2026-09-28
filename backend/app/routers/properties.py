"""GET /api/properties."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from db import REVIEWS

from ..db import aggregate
from ..schemas import Property
from ..services.catalog import list_properties
from ..services.query import r2

router = APIRouter(tags=["properties"])


@router.get("/properties", response_model=list[Property])
def properties() -> list[dict[str, Any]]:
    """All properties with the all-time review count and average score in our dataset."""
    pipeline = [{"$group": {"_id": "$property_id", "n": {"$sum": 1}, "avg": {"$avg": "$score"}}}]
    stats = {row["_id"]: row for row in aggregate(REVIEWS, pipeline)}
    out = []
    for prop in list_properties():
        s = stats.get(prop["id"])
        out.append(
            {
                "id": prop["id"],
                "name": prop["name"],
                "short_name": prop["short_name"],
                "booking_url": prop["booking_url"],
                "booking_score": r2(prop["booking_score"]),
                "total_reviews": int(s["n"]) if s else 0,
                "avg_score": r2(s["avg"]) if s else None,
            }
        )
    return out
