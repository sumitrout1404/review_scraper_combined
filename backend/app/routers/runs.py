"""GET /api/scrape-runs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..schemas import ScrapeRun
from ..services.freshness import recent_runs

router = APIRouter(tags=["runs"])


@router.get("/scrape-runs", response_model=list[ScrapeRun])
def scrape_runs(limit: int = Query(20, ge=1, le=500)) -> list[dict[str, Any]]:
    """Most recent collection runs (one row per property per run), newest first."""
    return recent_runs(limit)
