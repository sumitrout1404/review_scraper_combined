"""Strategy 3 (last resort): render the reviews panel and parse the DOM cards.

Slow (10 reviews per click) and lower fidelity – no Booking review id (ids fall
back to content hashes), no language, truncated hotel responses – but it only
depends on what a human visitor sees.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from collector.errors import ResponseShapeError, TransientFetchError
from collector.fetchers.base import ReviewSource, Throttle
from collector.fetchers.browser import BrowserSession
from collector.models import PropertyMeta, RawPage
from collector.parsers.dom import CARD_SELECTOR, parse_review_cards
from collector.properties import Property
from collector.raw_capture import RawCapture
from collector.settings import Settings

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

DOM_PAGE_SIZE = 10
_OPEN_REVIEWS = ('[data-testid="fr-read-all-reviews"]', '[data-testid="review-score-read-all"]')
_SORTER = '[data-testid="reviews-sorter-component"]'
_LIST = '[data-testid="review-list-container"]'
_NEXT = f'{_LIST} button[aria-label="Next page"]'
_COOKIE_REJECT = "#onetrust-reject-all-handler"
_FIRST_CARD_TEXT_JS = f"() => (document.querySelector('{CARD_SELECTOR}') || {{}}).innerText || ''"
_CHANGED_JS = f"(prev) => ((document.querySelector('{CARD_SELECTOR}') || {{}}).innerText || '') !== prev"


class BrowserDomSource(ReviewSource):
    name = "browser_dom"
    page_size = DOM_PAGE_SIZE

    def __init__(self, settings: Settings, throttle: Throttle, capture: RawCapture, session: BrowserSession) -> None:
        self._settings = settings
        self._throttle = throttle
        self._capture = capture
        self._session = session

    def fetch_page(self, prop: Property, offset: int) -> RawPage:
        page = self._session.page_for(prop)
        state = self._session.state
        try:
            if not state.get("dom_ready"):
                self._open_sorted_panel(page)
                state["dom_ready"], state["dom_page"] = True, 1
            target = offset // DOM_PAGE_SIZE + 1
            if target < state["dom_page"]:
                raise ResponseShapeError("DOM strategy can only page forward")
            while state["dom_page"] < target:
                if not self._next_page(page):
                    return RawPage(strategy=self.name, offset=offset, candidates=[], total_count=None)
                state["dom_page"] += 1
            html = page.inner_html(_LIST)
        except ResponseShapeError:
            raise
        except Exception as exc:  # playwright timeouts / detached elements
            raise TransientFetchError(f"DOM interaction failed: {type(exc).__name__}") from exc
        self._capture.save(self.name, prop.id, offset, "html", html)
        meta = self._session.headline(prop)
        return RawPage(strategy=self.name, offset=offset, candidates=parse_review_cards(html),
                       total_count=meta.booking_review_count, meta=meta)

    def fetch_meta(self, prop: Property) -> PropertyMeta:
        return self._session.headline(prop)

    def _open_sorted_panel(self, page: Page) -> None:
        if page.locator(_COOKIE_REJECT).count():
            page.locator(_COOKIE_REJECT).first.click()
        opener = next((s for s in _OPEN_REVIEWS if page.locator(s).count()), None)
        if opener is None:
            raise ResponseShapeError("reviews panel trigger not found")
        self._throttle.wait()
        page.locator(opener).first.click()
        page.wait_for_selector(CARD_SELECTOR)
        if not page.locator(_SORTER).count():
            raise ResponseShapeError("review sorter not found")
        previous = page.evaluate(_FIRST_CARD_TEXT_JS)
        self._throttle.wait()
        page.select_option(_SORTER, "NEWEST_FIRST")
        try:
            page.wait_for_function(_CHANGED_JS, arg=previous, timeout=15_000)
        except Exception:  # noqa: BLE001 - the newest review may already be first
            logger.debug("first card unchanged after sorting newest-first")

    def _next_page(self, page: Page) -> bool:
        """Click 'Next page'; False when the last page is already shown."""
        button = page.locator(_NEXT)
        if not button.count() or button.first.is_disabled():
            return False
        previous = page.evaluate(_FIRST_CARD_TEXT_JS)
        self._throttle.wait()
        button.first.click()
        page.wait_for_function(_CHANGED_JS, arg=previous)
        return True

    def close(self) -> None:
        self._session.close()
