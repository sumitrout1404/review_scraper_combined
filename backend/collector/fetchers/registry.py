"""Build the ordered strategy list for this environment."""

from __future__ import annotations

import logging

from collector.fetchers.base import ReviewSource, Throttle
from collector.fetchers.browser import BrowserSession, playwright_available
from collector.fetchers.http_graphql import HttpGraphQLSource
from collector.raw_capture import RawCapture
from collector.settings import BROWSER_STRATEGIES, Settings

logger = logging.getLogger(__name__)


def build_sources(settings: Settings, throttle: Throttle) -> tuple[list[ReviewSource], BrowserSession | None]:
    """Instantiate the configured strategies in order, skipping browser ones if Playwright is absent.

    Returns the sources and the shared browser session (None when no browser strategy is enabled).
    """
    capture = RawCapture(settings.debug_dir, settings.save_raw)
    wants_browser = any(s in BROWSER_STRATEGIES for s in settings.strategies)
    session: BrowserSession | None = None
    if wants_browser and playwright_available():
        session = BrowserSession(settings, throttle)
    elif wants_browser:
        logger.info("playwright not installed: browser fallbacks disabled (HTTP strategy only)")

    sources: list[ReviewSource] = []
    for name in settings.strategies:
        if name == "http_graphql":
            sources.append(HttpGraphQLSource(settings, throttle, capture))
        elif session is not None and name == "browser_graphql":
            from collector.fetchers.browser_graphql import BrowserGraphQLSource

            sources.append(BrowserGraphQLSource(settings, throttle, capture, session))
        elif session is not None and name == "browser_dom":
            from collector.fetchers.browser_dom import BrowserDomSource

            sources.append(BrowserDomSource(settings, throttle, capture, session))
    return sources, session
