"""GET /api/trends."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from ..deps import Filters, common_filters
from ..schemas import Trends
from ..services.trends import score_trends

router = APIRouter(tags=["trends"])


@router.get("/trends", response_model=Trends)
def trends(
    granularity: Literal["week", "month"] = Query("week"),
    f: Filters = Depends(common_filters),
) -> dict[str, Any]:
    """Score and sentiment per week/month; empty periods are included with count 0.

    Without dates: the last 26 weeks / 12 months up to today (trimmed to the first review).
    """
    return score_trends(f, granularity)
