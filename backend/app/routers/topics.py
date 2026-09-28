"""GET /api/topics, /api/topics/breakdown, /api/topics/trends."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from ..deps import MAX_LIST_PARAM, Filters, common_filters, parse_csv
from ..schemas import Topic, TopicBreakdown, TopicTrends
from ..services.catalog import topic_catalog
from ..services.topic_report import build_breakdown
from ..services.trends import topic_trends as build_topic_trends

router = APIRouter(tags=["topics"])


@router.get("/topics", response_model=list[Topic])
def topics() -> list[dict[str, Any]]:
    """Topic catalogue ordered by sort_order."""
    return topic_catalog()


@router.get("/topics/breakdown", response_model=TopicBreakdown)
def breakdown(f: Filters = Depends(common_filters)) -> dict[str, Any]:
    """Complaints/praise per topic for the filters (all dates when none are given)."""
    return build_breakdown(f)


@router.get("/topics/trends", response_model=TopicTrends)
def topic_trends(
    granularity: Literal["week", "month"] = Query("week"),
    polarity: Literal["negative", "positive"] = Query("negative"),
    topic: str | None = Query(None, max_length=MAX_LIST_PARAM, description="Optional comma-separated topic keys"),
    f: Filters = Depends(common_filters),
) -> dict[str, Any]:
    """Mentions per period per topic (same default window as /api/trends)."""
    return build_topic_trends(f, granularity, polarity, parse_csv(topic, "topic"))
