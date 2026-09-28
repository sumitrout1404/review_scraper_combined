"""GET /api/cron/collect – protected endpoint triggered by Vercel Cron."""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..services.cron_job import JobUnavailable, run_cron_job

router = APIRouter(tags=["cron"], include_in_schema=False)
logger = logging.getLogger(__name__)
NO_STORE = {"Cache-Control": "no-store"}


def _authorised(header: str | None, secret: str) -> bool:
    """Constant-time check of ``Authorization: Bearer <secret>``."""
    expected = f"Bearer {secret}".encode()
    return hmac.compare_digest((header or "").encode(), expected)


def _reply(status: int, body: dict) -> JSONResponse:
    return JSONResponse(status_code=status, content=body, headers=NO_STORE)


@router.get("/cron/collect")
def cron_collect(request: Request) -> JSONResponse:
    """Run an incremental collection followed by analysis, under the DB lease."""
    settings = get_settings()
    request_id = getattr(request.state, "request_id", "-")
    if not settings.cron_secret:
        return _reply(503, {"detail": "Cron is not configured (CRON_SECRET is unset)"})
    if not _authorised(request.headers.get("authorization"), settings.cron_secret):
        logger.warning("Rejected cron call with bad credentials request_id=%s", request_id)
        return _reply(401, {"detail": "Unauthorized"})
    try:
        return _reply(200, run_cron_job(settings, request_id))
    except JobUnavailable as exc:
        logger.error("Cron collect unavailable request_id=%s: %s", request_id, exc)
        return _reply(503, {"detail": "Collector is not available in this deployment"})
    except Exception:
        logger.exception("Cron collect failed request_id=%s", request_id)
        return _reply(500, {"detail": "Collection failed; see server logs", "status": "failed"})
