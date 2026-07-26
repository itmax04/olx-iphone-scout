"""F-10: чистый парсер на санитизированных fixtures; U-06..U-08."""

from decimal import Decimal

import pytest

from apps.monitoring.collectors.exceptions import CaptchaError, LayoutChangedError
from apps.monitoring.collectors.fixture_source import load_fixture_html
from apps.monitoring.collectors.olx_parser import (
    parse_detail_page,
    parse_price,
    parse_search_page,
)

DETAIL_URL = "https://www.olx.ua/d/uk/obyavlenie/iphone-13-ID800000001.html"


class TestPriceParsing:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("11 500 грн.", Decimal("11500.00")),
            ("12 500 грн", Decimal("12500.00")),
            ("150 грн.", Decimal("150.00")),
            ("Договірна", None),
            ("Обмен", None),
            ("", None),
        ],
    )
    def test_parse_price_uah(self, text, expected):
        price, currency = parse_price(text)
        assert price == expected
        assert currency == "UAH"

    def test_usd_detected(self):
        price, currency = parse_price("450 $")
        assert price == Decimal("450.00")
        assert currency == "USD"

    def test_negative_and_huge_rejected(self):
        assert parse_price("999999999999 грн")[0] is None  # U-07


class TestSearchPage:
    def test_normal(self):
        result = parse_search_page(load_fixture_html("search_normal"))
        assert len(result.cards) == 4
        first = result.cards[0]
        assert first.olx_id == "800000001"
        assert first.price_uah == Decimal("11500.00")
        assert first.url.startswith("https://www.olx.ua/")
        assert "Оболонський" in first.location  # U-08: украинский текст не поврежден

    def test_promoted_card_flag(self):
        result = parse_search_page(load_fixture_html("search_promoted"))
        assert result.cards[0].is_promoted is True
        assert result.cards[1].is_promoted is False

    def test_missing_price_card(self):
        result = parse_search_page(load_fixture_html("search_missing_price"))
        prices = {card.olx_id: card.price_uah for card in result.cards}
        assert prices["800000021"] is None
        assert prices["800000022"] == Decimal("13900.00")

    def test_max_cards_respected(self):
        result = parse_search_page(load_fixture_html("search_normal"), max_cards=2)
        assert len(result.cards) == 2

    def test_captcha_detected(self):
        with pytest.raises(CaptchaError):
            parse_search_page(load_fixture_html("captcha"))

    def test_layout_changed(self):
        with pytest.raises(LayoutChangedError):
            parse_search_page("<html><body><p>другая верстка</p></body></html>")


class TestDetailPage:
    def test_normal(self):
        result = parse_detail_page(load_fixture_html("detail_normal"), DETAIL_URL)
        assert result.is_active is True
        detail = result.detail
        assert detail.olx_id == "800000001"
        assert detail.price_uah == Decimal("11500.00")
        assert "АКБ 87%" in detail.description
        assert detail.delivery_available is True
        assert detail.seller_type == "PRIVATE"
        assert len(detail.photo_urls) == 2
        assert all(url.startswith("https://") for url in detail.photo_urls)

    def test_inactive(self):
        result = parse_detail_page(load_fixture_html("detail_inactive"), DETAIL_URL)
        assert result.is_active is False
        assert result.detail is None

    def test_captcha_on_detail(self):
        with pytest.raises(CaptchaError):
            parse_detail_page(load_fixture_html("captcha"), DETAIL_URL)

    def test_layout_changed_on_detail(self):
        with pytest.raises(LayoutChangedError):
            parse_detail_page("<html><body>ничего</body></html>", DETAIL_URL)
