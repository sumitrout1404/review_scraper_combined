"""GET /api/summary."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..deps import Filters, common_filters
from ..schemas import Summary
from ..services.summary import build_summary

router = APIRouter(tags=["summary"])


@router.get("/summary", response_model=Summary)
def summary(f: Filters = Depends(common_filters)) -> dict[str, Any]:
    """Current window vs the previous window of the same length directly before it.

    Defaults to the current Sydney week to date (Monday -> today).
    """
    return build_summary(f)
