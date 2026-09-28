"""Strategy 2: the same ReviewList GraphQL query, issued from inside a real browser page.

Used when plain HTTP gets challenged/blocked: the request then carries the
browser's WAF token and TLS fingerprint. Hotel ids are re-discovered from the page.
"""

from __future__ import annotations

from collector.booking.queries import CLIENT_HEADERS, GRAPHQL_PATH, build_payload, unwrap_review_list
from collector.errors import TransientFetchError
from collector.fetchers.base import ReviewSource, Throttle
from collector.fetchers.browser import BrowserSession
from collector.fetchers.http_graphql import classify_response
from collector.models import PropertyMeta, RawPage
from collector.parsers.graphql import parse_review_list
from collector.properties import Property
from collector.raw_capture import RawCapture
from collector.settings import Settings

_FETCH_JS = """
async ([url, body, headers, timeoutMs]) => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, {method: 'POST', headers, body: JSON.stringify(body),
                                credentials: 'include', signal: ctrl.signal});
    return {status: r.status, text: await r.text(), retryAfter: r.headers.get('retry-after')};
  } catch (e) {
    return {status: 0, text: String(e), retryAfter: null};
  } finally {
    clearTimeout(timer);
  }
}
"""


class BrowserGraphQLSource(ReviewSource):
    name = "browser_graphql"

    def __init__(self, settings: Settings, throttle: Throttle, capture: RawCapture, session: BrowserSession) -> None:
        self._settings = settings
        self._throttle = throttle
        self._capture = capture
        self._session = session
        self.page_size = settings.page_size

    def fetch_page(self, prop: Property, offset: int) -> RawPage:
        page = self._session.page_for(prop)
        payload = build_payload(prop, offset, self.page_size, hotel_id=self._session.hotel_id, ufi=self._session.ufi)
        url = f"{GRAPHQL_PATH}?lang={self._settings.booking_lang}"
        self._throttle.wait()
        try:
            response = page.evaluate(_FETCH_JS, [url, payload, CLIENT_HEADERS, self._settings.http_timeout_s * 1000])
        except Exception as exc:  # playwright Error: page crashed / navigation mid-call
            raise TransientFetchError(f"in-page fetch failed: {type(exc).__name__}") from exc
        text = str(response.get("text", ""))
        if int(response.get("status", 0)) == 0:
            raise TransientFetchError(f"in-page fetch failed: {text[:200]}")
        self._capture.save(self.name, prop.id, offset, "json", text)
        headers = {"retry-after": response.get("retryAfter") or ""}
        body = classify_response(int(response.get("status", 0)), text, headers)
        candidates, total = parse_review_list(unwrap_review_list(body))
        return RawPage(strategy=self.name, offset=offset, candidates=candidates, total_count=total)

    def fetch_meta(self, prop: Property) -> PropertyMeta:
        return self._session.headline(prop)

    def close(self) -> None:
        self._session.close()
