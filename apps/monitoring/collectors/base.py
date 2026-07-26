"""ListingSource protocol: production and fixture sources implement it."""

from typing import Protocol

from apps.monitoring.collectors.dto import ListingDetailResult, SearchPageResult


class ListingSource(Protocol):
    def fetch_search(self, url: str, *, max_cards: int) -> SearchPageResult: ...

    def fetch_detail(self, canonical_url: str) -> ListingDetailResult: ...

    def close(self) -> None: ...
