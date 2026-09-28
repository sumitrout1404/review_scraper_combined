"""Shared headless-Chromium session (Playwright, optional dependency).

Loading the hotel page in a real browser lets AWS WAF's JavaScript challenge
resolve by itself (spike: ~3-8 s). The session keeps one page per property
loaded so both browser strategies and the headline-score probe reuse it.
Nothing from the browser (cookies, storage) is ever written to disk.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from collector.errors import BlockedError, StrategyUnavailableError, TransientFetchError
from collector.fetchers.base import Throttle
from collector.models import PropertyMeta
from collector.properties import Property
from collector.settings import Settings

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import Browser, Page, Playwright

logger = logging.getLogger(__name__)

_READY_MARKER = "b_hotel_id"  # present in the real hotel page's inline config, absent on the challenge page
_POLL_INTERVAL_S = 1.0


def playwright_available() -> bool:
    """True if the optional Playwright package can be imported."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


class BrowserSession:
    """Lazily started Chromium with one resolved hotel page at a time."""

    def __init__(self, settings: Settings, throttle: Throttle) -> None:
        self._settings = settings
        self._throttle = throttle
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._property_id: str | None = None
        self._html: str = ""
        self.hotel_id: int | None = None
        self.ufi: int | None = None
        self.state: dict[str, Any] = {}  # per-page scratch space for strategies (reset on navigation)

    # -- lifecycle -------------------------------------------------------------

    def _start(self) -> None:
        if self._browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise StrategyUnavailableError("playwright is not installed") from exc
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=self._settings.headless)
        except Exception as exc:  # missing browser binary etc.
            self.close()
            raise StrategyUnavailableError(f"cannot launch chromium: {exc}") from exc

    def close(self) -> None:
        """Close the browser; safe to call repeatedly."""
        try:
            if self._browser is not None:
                self._browser.close()
            if self._pw is not None:
                self._pw.stop()
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            logger.debug("browser cleanup: %s", exc)
        self._browser = self._pw = self._page = None
        self._property_id = None

    # -- navigation ------------------------------------------------------------

    def page_for(self, prop: Property) -> Page:
        """Return a page with ``prop``'s hotel page loaded and the bot challenge resolved."""
        from collector.parsers.dom import parse_hotel_ids

        if self._page is not None and self._property_id == prop.id:
            return self._page
        self._start()
        assert self._browser is not None
        if self._page is not None:
            self._page.context.close()
        context = self._browser.new_context(
            locale="en-GB",
            user_agent=self._settings.user_agent,
            viewport={"width": 1366, "height": 900},
        )
        context.set_default_timeout(self._settings.browser_timeout_s * 1000)
        self._page = context.new_page()
        self._property_id = None
        self.state = {}
        self._throttle.wait()
        try:
            self._page.goto(prop.localized_url(self._settings.booking_lang), wait_until="domcontentloaded")
            self._html = self._wait_for_challenge()
        except BlockedError:
            raise
        except Exception as exc:  # playwright TimeoutError / Error
            raise TransientFetchError(f"browser navigation failed: {type(exc).__name__}") from exc
        self.hotel_id, self.ufi = parse_hotel_ids(self._html)
        if self.hotel_id and self.hotel_id != prop.hotel_id:
            logger.warning("%s: page reports hotel_id %s, config has %s", prop.id, self.hotel_id, prop.hotel_id)
        self._property_id = prop.id
        return self._page

    def _wait_for_challenge(self) -> str:
        assert self._page is not None
        deadline = time.monotonic() + self._settings.challenge_timeout_s
        while True:
            html = self._page.content()
            if _READY_MARKER in html:
                # The challenge reloads the page; let that document finish before using it.
                try:
                    self._page.wait_for_load_state("load", timeout=self._settings.challenge_timeout_s * 1000)
                except Exception as exc:  # noqa: BLE001 - slow third-party assets are fine
                    logger.debug("load state not reached: %s", exc)
                return self._page.content()
            if time.monotonic() > deadline:
                raise BlockedError("WAF challenge did not resolve in the browser")
            self._page.wait_for_timeout(_POLL_INTERVAL_S * 1000)

    def headline(self, prop: Property) -> PropertyMeta:
        """Booking's headline score/count parsed from the resolved hotel page."""
        from collector.parsers.dom import parse_headline

        self.page_for(prop)
        return parse_headline(self._html)
