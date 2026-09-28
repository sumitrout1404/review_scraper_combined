"""Detect Booking/AWS WAF bot challenges and block pages in HTTP responses."""

from __future__ import annotations

_CHALLENGE_MARKERS = (
    "awswafcookiedomainlist",  # AWS WAF JS challenge bootstrap
    "/challenge.js",
    "gokuprops",  # AWS WAF captcha
    "captcha-container",
)
_BLOCK_MARKERS = (
    "access denied",
    "request blocked",
    "unusual traffic",
)
CHALLENGE_STATUS_CODES = frozenset({202, 405})


def looks_like_challenge(status_code: int, body: str) -> bool:
    """True if the response is a bot challenge / block page rather than content.

    AWS WAF answers challenged requests with HTTP 202 (JS challenge) or 405 (captcha)
    and a tiny HTML bootstrap. A real hotel page also embeds the WAF domain list, so
    for large 200 pages we only treat it as a challenge when the page content is absent.
    """
    head = body[:20_000].casefold()
    has_marker = any(m in head for m in _CHALLENGE_MARKERS)
    if status_code in CHALLENGE_STATUS_CODES and has_marker:
        return True
    if status_code == 403:
        return True
    if has_marker and len(body) < 50_000:
        return True
    return any(m in head for m in _BLOCK_MARKERS) and len(body) < 50_000
