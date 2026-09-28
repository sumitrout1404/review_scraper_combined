"""HTTP hardening: request ids, error masking, security headers, method/size limits, rate limiting."""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .config import Settings

logger = logging.getLogger("app.http")

ALLOWED_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'"
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
HSTS = "max-age=63072000; includeSubDomains"
MAX_TRACKED_CLIENTS = 10_000
NO_CACHE_PREFIXES = ("/api/health", "/api/cron")

CallNext = Callable[[Request], Awaitable[Response]]


class TokenBucketLimiter:
    """Thread-safe in-memory token bucket per client key.

    State lives in process memory, so on serverless it is per instance (best effort).
    """

    def __init__(self, rate_per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(rate_per_minute)
        self.refill_per_sec = rate_per_minute / 60.0
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str) -> float:
        """Take one token. Returns 0 if allowed, else seconds until a token is available."""
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_sec)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                if len(self._buckets) > MAX_TRACKED_CLIENTS:
                    self._prune(now)
                return 0.0
            self._buckets[key] = (tokens, now)
            return (1 - tokens) / self.refill_per_sec

    def _prune(self, now: float) -> None:
        full_after = self.capacity / self.refill_per_sec
        for key, (_, last) in list(self._buckets.items()):
            if now - last >= full_after:
                del self._buckets[key]


def client_ip(request: Request) -> str:
    """Best-effort client IP (Vercel sets x-forwarded-for / x-real-ip)."""
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail}, headers=headers)


def install_security(app: FastAPI, settings: Settings) -> None:
    """Register the hardening middleware on ``app`` (outermost first in execution order)."""
    limiter = TokenBucketLimiter(settings.rate_limit_per_minute) if settings.rate_limit_per_minute > 0 else None

    @app.middleware("http")
    async def guard(request: Request, call_next: CallNext) -> Response:
        if request.method not in ALLOWED_METHODS:
            return _error(405, "Method not allowed", {"Allow": "GET, HEAD, OPTIONS"})
        if len(str(request.url)) > settings.max_url_length:
            return _error(414, "Request URL too long")
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > settings.max_body_bytes):
            return _error(413, "Request body too large")
        if limiter is not None and request.method != "OPTIONS":
            wait = limiter.acquire(client_ip(request))
            if wait > 0:
                return _error(429, "Too many requests, please slow down", {"Retry-After": str(math.ceil(wait))})
        return await call_next(request)

    @app.middleware("http")
    async def headers_and_errors(request: Request, call_next: CallNext) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if 0 < len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled error request_id=%s method=%s path=%s", request_id, request.method, request.url.path
            )
            response = _error(500, "Internal server error")
        is_docs = not settings.is_production and request.url.path.startswith(DOCS_PATHS)
        h = response.headers
        h["X-Request-ID"] = request_id
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = PERMISSIONS_POLICY
        h["Cross-Origin-Resource-Policy"] = "cross-origin"
        h["Content-Security-Policy"] = DOCS_CSP if is_docs else API_CSP
        if settings.is_production:
            h["Strict-Transport-Security"] = HSTS
        if "cache-control" not in h:
            cacheable = request.method in ("GET", "HEAD") and response.status_code == 200
            cacheable = cacheable and not request.url.path.startswith(NO_CACHE_PREFIXES)
            h["Cache-Control"] = f"public, max-age={settings.cache_max_age}" if cacheable else "no-store"
        return response
