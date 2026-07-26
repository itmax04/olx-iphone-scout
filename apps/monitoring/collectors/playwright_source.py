"""Production ListingSource: Playwright Chromium over public OLX pages.

Rules enforced here:
- concurrency 1 (a single page at a time);
- navigation only to validated OLX hosts, final URL re-checked;
- no OLX login, no cookies reuse, no fingerprint spoofing;
- browser restarted after N scans or on critical errors;
- the browser is always closed in error paths.
"""

import logging
from urllib.parse import urlsplit

from django.conf import settings

from apps.monitoring.collectors.dto import ListingDetailResult, SearchPageResult
from apps.monitoring.collectors.exceptions import (
    BlockedError,
    CollectorError,
    DisallowedNavigationError,
    NavigationTimeoutError,
    OlxRateLimitedError,
)
from apps.monitoring.collectors.olx_parser import parse_detail_page, parse_search_page
from apps.monitoring.validators import validate_olx_url

logger = logging.getLogger(__name__)


class PlaywrightOlxSource:
    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._scan_count = 0

    # -- lifecycle ---------------------------------------------------------

    def _ensure_browser(self):
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=settings.PLAYWRIGHT_HEADLESS,
        )
        logger.info("collector_browser_started", extra={"event": "browser_started"})

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:  # pragma: no cover - best effort shutdown
            logger.warning("collector_browser_close_failed")
        finally:
            self._browser = None
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:  # pragma: no cover
            pass
        finally:
            self._playwright = None

    def _restart_if_needed(self) -> None:
        self._scan_count += 1
        if self._scan_count >= settings.OLX_BROWSER_RESTART_AFTER_SCANS:
            logger.info("collector_browser_restart", extra={"event": "browser_restart"})
            self.close()
            self._scan_count = 0

    # -- fetching ----------------------------------------------------------

    def _fetch_html(self, url: str) -> str:
        validate_olx_url(url, check_dns=True)
        self._ensure_browser()
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        context = self._browser.new_context()
        page = context.new_page()
        try:
            try:
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=settings.OLX_NAVIGATION_TIMEOUT_MS,
                )
            except PlaywrightTimeout:
                raise NavigationTimeoutError()

            final_host = urlsplit(page.url).hostname or ""
            try:
                validate_olx_url(page.url, check_dns=False)
            except Exception:
                raise DisallowedNavigationError(
                    f"Redirect ушел на неразрешенный host: {final_host}"
                )

            status = response.status if response is not None else 0
            if status == 403:
                raise BlockedError()
            if status == 429:
                raise OlxRateLimitedError()
            if status >= 500:
                raise CollectorError(f"OLX вернул статус {status}.")
            return page.content()
        finally:
            try:
                page.close()
                context.close()
            except Exception:  # pragma: no cover - already closing
                pass

    def fetch_search(self, url: str, *, max_cards: int) -> SearchPageResult:
        try:
            html = self._fetch_html(url)
        except CollectorError:
            raise
        except Exception as exc:
            self.close()
            raise CollectorError(f"Сбой браузера: {type(exc).__name__}")
        result = parse_search_page(html, max_cards=max_cards)
        self._restart_if_needed()
        return result

    def fetch_detail(self, canonical_url: str) -> ListingDetailResult:
        try:
            html = self._fetch_html(canonical_url)
        except CollectorError:
            raise
        except Exception as exc:
            self.close()
            raise CollectorError(f"Сбой браузера: {type(exc).__name__}")
        result = parse_detail_page(html, canonical_url)
        self._restart_if_needed()
        return result
