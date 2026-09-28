"""GET /api/health and /api/meta."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from db import REVIEWS

from ..config import get_settings
from ..db import DB_ERRORS, UNAVAILABLE_MESSAGE, DatabaseUnavailable, ping, ro
from ..schemas import Health, Meta
from ..services.dates import sydney_today, week_start
from ..services.freshness import last_run, last_scraped_at

router = APIRouter(tags=["meta"])


def _unavailable(exc: Exception) -> JSONResponse:
    """503 with enough to diagnose a deployment without revealing any configuration.

    ``db_configured`` says only whether a connection string is present, and ``reason``
    is the exception class name -- never a URI, host, credential or stack trace.
    """
    body = {
        "status": "error",
        "config_ok": get_settings().config_ok,
        "db": None,
        "db_configured": bool(os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URI_READONLY")),
        "reason": type(exc).__name__,
        "detail": UNAVAILABLE_MESSAGE,
    }
    return JSONResponse(status_code=503, content=body)


@router.get("/health", response_model=Health)
def health() -> dict[str, Any] | JSONResponse:
    """Liveness, config sanity (no values) and DB status (review count, last cron run).

    Returns 503 when the database is unavailable.
    """
    try:
        ping()
        return {
            "status": "ok",
            "config_ok": get_settings().config_ok,
            "db": {
                "dialect": "mongodb",
                "reviews": ro(REVIEWS).estimated_document_count(),
                "last_scraped_at": last_scraped_at(),
                "last_cron_run": last_run(trigger="cron"),
            },
        }
    except (DatabaseUnavailable, *DB_ERRORS) as exc:
        return _unavailable(exc)


@router.get("/meta", response_model=Meta)
def meta() -> dict[str, Any]:
    """Dates and freshness info the dashboard needs to label its filters."""
    today = sydney_today()
    reviews = ro(REVIEWS)
    oldest = reviews.find_one({}, {"review_date": 1}, sort=[("review_date", 1)])
    newest = reviews.find_one({}, {"review_date": 1}, sort=[("review_date", -1)])
    latest = last_run()
    return {
        "today": today.isoformat(),
        "this_week_start": week_start(today).isoformat(),
        "min_review_date": oldest["review_date"] if oldest else None,
        "max_review_date": newest["review_date"] if newest else None,
        "last_scraped_at": last_scraped_at(),
        "last_run_status": latest["status"] if latest else None,
        "total_reviews": reviews.count_documents({}),
    }
