"""Strategy 1 (cheapest): POST Booking's public ReviewList GraphQL query with plain httpx.

Spike result (2026-09-28): the hotel HTML pages are behind an AWS WAF JS challenge
(HTTP 202) for non-browser clients, but ``/dml/graphql`` answers plain HTTPS
requests with JSON, so no browser, cookies or session are needed on the happy path.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from collector.booking.queries import CLIENT_HEADERS, GRAPHQL_PATH, build_payload, unwrap_review_list
from collector.errors import BlockedError, FetchError, ResponseShapeError, TransientFetchError
from collector.fetchers.base import ReviewSource, Throttle
from collector.models import RawPage
from collector.parsers.challenge import looks_like_challenge
from collector.parsers.graphql import parse_review_list
from collector.properties import Property
from collector.raw_capture import RawCapture
from collector.settings import BOOKING_BASE_URL, Settings

logger = logging.getLogger(__name__)


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a numeric ``Retry-After`` header (HTTP-date form is ignored)."""
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        return None


def classify_response(status: int, text: str, headers: httpx.Headers | dict[str, str]) -> Any:
    """Map an HTTP response to parsed JSON or the right collector exception."""
    if status == 429:
        raise TransientFetchError("HTTP 429 Too Many Requests", retry_after=parse_retry_after(headers.get("retry-after")))
    if status >= 500:
        raise TransientFetchError(f"HTTP {status}", retry_after=parse_retry_after(headers.get("retry-after")))
    if looks_like_challenge(status, text):
        raise BlockedError(f"bot challenge / block page (HTTP {status})")
    if status >= 400:
        raise FetchError(f"HTTP {status}")
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ResponseShapeError(f"non-JSON response (HTTP {status}, {len(text)} bytes)") from exc


class HttpGraphQLSource(ReviewSource):
    """Fetch review pages via the GraphQL endpoint with a plain HTTP client."""

    name = "http_graphql"

    def __init__(self, settings: Settings, throttle: Throttle, capture: RawCapture,
                 client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._throttle = throttle
        self._capture = capture
        self.page_size = settings.page_size
        self._client = client or httpx.Client(
            base_url=BOOKING_BASE_URL,
            timeout=httpx.Timeout(settings.http_timeout_s),
            headers={
                "user-agent": settings.user_agent,
                "accept-language": settings.accept_language,
                "origin": BOOKING_BASE_URL,
                **CLIENT_HEADERS,
            },
            follow_redirects=False,
        )

    def fetch_page(self, prop: Property, offset: int) -> RawPage:
        payload = build_payload(prop, offset, self.page_size)
        self._throttle.wait()
        try:
            response = self._client.post(
                GRAPHQL_PATH,
                params={"lang": self._settings.booking_lang},
                json=payload,
                headers={"referer": prop.localized_url(self._settings.booking_lang)},
            )
        except httpx.TimeoutException as exc:
            raise TransientFetchError(f"timeout: {type(exc).__name__}") from exc
        except httpx.TransportError as exc:
            raise TransientFetchError(f"transport error: {type(exc).__name__}") from exc
        self._capture.save(self.name, prop.id, offset, "json", response.text)
        body = classify_response(response.status_code, response.text, response.headers)
        result = unwrap_review_list(body)
        candidates, total = parse_review_list(result)
        return RawPage(strategy=self.name, offset=offset, candidates=candidates, total_count=total)

    def close(self) -> None:
        self._client.close()
