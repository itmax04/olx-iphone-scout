"""Pure HTML parser for OLX pages. No ORM, no network, no Playwright imports."""

import re
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from apps.monitoring.collectors import selectors as sel
from apps.monitoring.collectors.dto import (
    ListingDetailDTO,
    ListingDetailResult,
    SearchCardDTO,
    SearchPageResult,
)
from apps.monitoring.collectors.exceptions import CaptchaError, LayoutChangedError
from apps.monitoring.validators import extract_olx_id

_PRICE_DIGITS = re.compile(r"\d[\d\s  .,]*")
_NEGOTIABLE_MARKERS = ("договірна", "договорная", "обмін", "обмен")


def detect_captcha(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in sel.CAPTCHA_MARKERS)


def parse_price(text: str) -> tuple[Decimal | None, str]:
    """Parse '11 500 грн.' style price text -> (Decimal or None, currency)."""
    cleaned = (text or "").strip().lower()
    if not cleaned or any(marker in cleaned for marker in _NEGOTIABLE_MARKERS):
        return None, "UAH"
    currency = "UAH"
    if "$" in cleaned or "usd" in cleaned:
        currency = "USD"
    elif "€" in cleaned or "eur" in cleaned:
        currency = "EUR"
    elif "грн" not in cleaned and "uah" not in cleaned:
        currency = "UNK"
    match = _PRICE_DIGITS.search(cleaned)
    if not match:
        return None, currency
    digits = re.sub(r"[\s  ]", "", match.group(0))
    # OLX shows whole UAH; a trailing ",00"/".00" fraction is tolerated.
    digits = re.sub(r"[.,]00$", "", digits)
    digits = digits.replace(",", ".")
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None, currency
    if value < 0 or value > Decimal("99999999"):
        return None, currency
    return value.quantize(Decimal("0.01")), currency


def _absolute_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return "https://www.olx.ua" + (href if href.startswith("/") else "/" + href)


def parse_search_page(html: str, *, max_cards: int = 50) -> SearchPageResult:
    if detect_captcha(html):
        raise CaptchaError()
    soup = BeautifulSoup(html, "html.parser")
    grid = soup.select_one(sel.SEARCH_GRID)
    if grid is None:
        if soup.select_one(sel.SEARCH_EMPTY_MARKER) is not None:
            return SearchPageResult(cards=(), parser_version=sel.PARSER_VERSION, total_visible=0)
        raise LayoutChangedError()

    cards: list[SearchCardDTO] = []
    raw_cards = grid.select(sel.SEARCH_CARD)
    for raw in raw_cards:
        if len(cards) >= max_cards:
            break
        link = raw.select_one(sel.CARD_LINK)
        href = link.get("href", "") if link else ""
        url = _absolute_url(str(href)) if href else ""
        olx_id = str(raw.get("id") or "") or (extract_olx_id(url) or "")
        title_el = raw.select_one(sel.CARD_TITLE)
        title = title_el.get_text(strip=True) if title_el else ""
        if not olx_id or not url or not title:
            continue  # a card without identity is diagnostics, not data
        price_el = raw.select_one(sel.CARD_PRICE)
        price, currency = parse_price(price_el.get_text(" ", strip=True) if price_el else "")
        location_el = raw.select_one(sel.CARD_LOCATION_DATE)
        location = ""
        if location_el:
            location = location_el.get_text(" ", strip=True).split(" - ")[0].strip()
        image = raw.select_one(sel.CARD_IMAGE)
        thumbnail = str(image.get("src") or "") if image else ""
        if thumbnail and not thumbnail.startswith("https://"):
            thumbnail = ""
        promoted = raw.select_one(sel.CARD_PROMOTED_MARKER) is not None
        cards.append(
            SearchCardDTO(
                olx_id=olx_id,
                url=url,
                title=title[:255],
                price_uah=price,
                currency=currency,
                location=location[:255],
                thumbnail_url=thumbnail[:2048],
                is_promoted=promoted,
            )
        )
    if not raw_cards:
        raise LayoutChangedError("Контейнер выдачи найден, но карточки отсутствуют в ожидаемой разметке.")
    return SearchPageResult(
        cards=tuple(cards), parser_version=sel.PARSER_VERSION, total_visible=len(raw_cards)
    )


def parse_detail_page(html: str, url: str) -> ListingDetailResult:
    if detect_captcha(html):
        raise CaptchaError()
    soup = BeautifulSoup(html, "html.parser")

    if soup.select_one(sel.DETAIL_INACTIVE_MARKER) is not None:
        return ListingDetailResult(detail=None, is_active=False, parser_version=sel.PARSER_VERSION)

    title_el = soup.select_one(sel.DETAIL_TITLE)
    if title_el is None:
        raise LayoutChangedError("Заголовок объявления не найден на detail-странице.")
    title = title_el.get_text(strip=True)

    price_el = soup.select_one(sel.DETAIL_PRICE)
    price, currency = parse_price(price_el.get_text(" ", strip=True) if price_el else "")

    description = ""
    description_el = soup.select_one(sel.DETAIL_DESCRIPTION)
    if description_el:
        description = description_el.get_text("\n", strip=True)[:20000]

    location = ""
    location_el = soup.select_one(sel.DETAIL_LOCATION)
    if location_el:
        location = location_el.get_text(" ", strip=True)[:255]

    seller_name = ""
    seller_el = soup.select_one(sel.DETAIL_SELLER_NAME)
    if seller_el:
        seller_name = seller_el.get_text(strip=True)[:120]

    seller_profile_url = ""
    seller_link = soup.select_one(sel.DETAIL_SELLER_LINK)
    if seller_link and seller_link.get("href"):
        candidate = _absolute_url(str(seller_link["href"]))
        if candidate.startswith("https://"):
            seller_profile_url = candidate[:2048]

    seller_joined_text = ""
    since_el = soup.select_one(sel.DETAIL_SELLER_SINCE)
    if since_el:
        seller_joined_text = since_el.get_text(" ", strip=True)[:120]

    seller_type = "PRIVATE"
    if soup.select_one(sel.DETAIL_SELLER_TYPE_BUSINESS) is not None:
        seller_type = "BUSINESS"

    delivery_available: bool | None = None
    if soup.select_one(sel.DETAIL_DELIVERY_BADGE) is not None:
        delivery_available = True

    photos: list[str] = []
    for img in soup.select(sel.DETAIL_PHOTO)[:20]:
        src = str(img.get("src") or "")
        if src.startswith("https://"):
            photos.append(src[:2048])

    olx_id = extract_olx_id(url) or ""

    detail = ListingDetailDTO(
        olx_id=olx_id,
        url=url,
        title=title[:255],
        price_uah=price,
        currency=currency,
        description=description,
        location=location,
        seller_name=seller_name,
        seller_profile_url=seller_profile_url,
        seller_type=seller_type,
        seller_joined_text=seller_joined_text,
        delivery_available=delivery_available,
        photo_urls=tuple(photos),
        is_active=True,
    )
    return ListingDetailResult(detail=detail, is_active=True, parser_version=sel.PARSER_VERSION)
