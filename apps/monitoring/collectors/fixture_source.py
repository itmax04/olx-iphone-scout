"""Fixture-backed ListingSource for tests, demo and local acceptance.

Reads only allow-listed files from tests/fixtures/olx; never the network.
"""

from pathlib import Path

from django.conf import settings

from apps.monitoring.collectors.dto import ListingDetailResult, SearchPageResult
from apps.monitoring.collectors.olx_parser import parse_detail_page, parse_search_page

FIXTURES_DIR = Path(settings.BASE_DIR) / "tests" / "fixtures" / "olx"

ALLOWED_FIXTURES = (
    "search_normal",
    "search_promoted",
    "search_missing_price",
    "search_price_drop",
    "detail_normal",
    "detail_price_drop",
    "detail_inactive",
    "captcha",
)


def load_fixture_html(name: str) -> str:
    if name not in ALLOWED_FIXTURES:
        raise ValueError(f"Unknown fixture name: {name!r}. Allowed: {ALLOWED_FIXTURES}")
    path = FIXTURES_DIR / f"{name}.html"
    return path.read_text(encoding="utf-8")


class FixtureOlxSource:
    """Serves predetermined fixture pages regardless of URL."""

    def __init__(
        self, search_fixture: str = "search_normal", detail_fixture: str = "detail_normal"
    ):
        self.search_fixture = search_fixture
        self.detail_fixture = detail_fixture
        self.search_calls = 0
        self.detail_calls = 0

    def fetch_search(self, url: str, *, max_cards: int) -> SearchPageResult:
        self.search_calls += 1
        html = load_fixture_html(self.search_fixture)
        return parse_search_page(html, max_cards=max_cards)

    def fetch_detail(self, canonical_url: str) -> ListingDetailResult:
        self.detail_calls += 1
        html = load_fixture_html(self.detail_fixture)
        return parse_detail_page(html, canonical_url)

    def close(self) -> None:  # pragma: no cover - nothing to release
        return None
