"""FastAPI application factory for the read-only Review Insights API."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .cache import MAX_BODY_BYTES, CachedResponse, ResponseCache, cache_key, is_cacheable_path
from .config import Settings, get_settings, load_dotenv_if_available
from .db import DB_ERRORS, UNAVAILABLE_MESSAGE
from .routers import cron, insights, meta, properties, reviews, runs, summary, topics, trends
from .security import install_security

API_PREFIX = "/api"
logger = logging.getLogger(__name__)


def _validation_message(exc: RequestValidationError) -> str:
    """Flatten FastAPI's error list into the contract's single `detail` string."""
    parts = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("query", "path", "body")]
        name = ".".join(loc) or "request"
        parts.append(f"Invalid value for '{name}': {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "Invalid request"


def install_response_cache(app: FastAPI, settings: Settings) -> None:
    """Serve repeat reads from memory for ``CACHE_MAX_AGE`` seconds.

    The data only changes on the nightly collection run, so the same dashboard query
    need not be recomputed for every visitor. ``X-Cache`` reports HIT or MISS.
    """
    if settings.cache_max_age <= 0:
        return
    cache = ResponseCache()
    app.state.response_cache = cache

    @app.middleware("http")
    async def response_cache(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method != "GET" or not is_cacheable_path(request.url.path):
            return await call_next(request)

        key = cache_key(request.url.path, request.url.query)
        hit = cache.get(key)
        if hit is not None:
            return Response(
                content=hit.body,
                status_code=hit.status_code,
                media_type=hit.content_type,
                headers={"X-Cache": "HIT"},
            )  # the security middleware adds the standard headers on the way out

        response = await call_next(request)
        if response.status_code != 200:
            return response

        # Starlette hands middleware a streaming wrapper, so the body has to be
        # collected before it can be cached or returned.
        body = b"".join([chunk async for chunk in response.body_iterator])
        headers = dict(response.headers)
        headers["X-Cache"] = "MISS"
        if len(body) <= MAX_BODY_BYTES:
            cache.set(
                key,
                CachedResponse(
                    status_code=response.status_code,
                    body=body,
                    content_type=headers.get("content-type"),
                    expires_at=time.monotonic() + settings.cache_max_age,
                ),
            )
        return Response(content=body, status_code=response.status_code, headers=headers)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. ``settings`` defaults to the environment."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or get_settings()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    docs = not settings.is_production
    app = FastAPI(
        title="Azzurro Review Insights API",
        version="1.0.0",
        description="Read-only API over Booking.com reviews for four Azzurro Hotels properties.",
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _validation_message(exc)})

    async def on_database_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Database error request_id=%s path=%s: %s",
            getattr(request.state, "request_id", "-"), request.url.path, type(exc).__name__,
        )  # fmt: skip
        return JSONResponse(status_code=503, content={"detail": UNAVAILABLE_MESSAGE})

    for error_type in DB_ERRORS:
        app.add_exception_handler(error_type, on_database_error)

    for module in (meta, properties, summary, trends, topics, insights, reviews, runs, cron):
        app.include_router(module.router, prefix=API_PREFIX)

    install_response_cache(app, settings)
    install_security(app, settings)
    allow_all = "*" in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else list(settings.cors_origins),
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["Content-Disposition", "X-Request-ID", "Retry-After"],
        allow_credentials=False,
        max_age=600,
    )
    return app


load_dotenv_if_available()  # local dev only; must run before settings/engine are first read
app = create_app()
