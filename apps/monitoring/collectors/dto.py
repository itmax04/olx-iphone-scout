"""Typed DTOs produced by the parser; no ORM objects cross this boundary."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SearchCardDTO:
    olx_id: str
    url: str
    title: str
    price_uah: Decimal | None
    currency: str
    location: str = ""
    thumbnail_url: str = ""
    is_promoted: bool = False


@dataclass(frozen=True, slots=True)
class SearchPageResult:
    cards: tuple[SearchCardDTO, ...]
    parser_version: str
    total_visible: int


@dataclass(frozen=True, slots=True)
class ListingDetailDTO:
    olx_id: str
    url: str
    title: str
    price_uah: Decimal | None
    currency: str
    description: str = ""
    location: str = ""
    seller_name: str = ""
    seller_profile_url: str = ""
    seller_type: str = "UNKNOWN"
    seller_joined_text: str = ""
    delivery_available: bool | None = None
    photo_urls: tuple[str, ...] = field(default_factory=tuple)
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class ListingDetailResult:
    detail: ListingDetailDTO | None
    is_active: bool
    parser_version: str
