"""GET /api/insights."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..deps import Filters, common_filters
from ..schemas import Insight
from ..services import insights as insights_service
from ..services.windows import summary_window

router = APIRouter(tags=["insights"])


@router.get("/insights", response_model=list[Insight])
def insights(f: Filters = Depends(common_filters)) -> list[dict[str, Any]]:
    """Plain-English statements ranked by severity. Same default window as /api/summary."""
    d_from, d_to = summary_window(f)
    return insights_service.generate(f, d_from, d_to)
