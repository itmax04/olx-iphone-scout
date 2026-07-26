"""E-07: рыночные цены и резервы через HTML-формы."""

import pytest
from django.utils import timezone

from apps.pricing.models import DefectReserveRule, MarketPriceRule

pytestmark = pytest.mark.django_db


def test_create_market_rule(admin_client_ru):
    response = admin_client_ru.post(
        "/prices/market/new/",
        {
            "model_key": "iphone_13",
            "storage_gb": "128",
            "sim_variant": "ANY",
            "expected_final_sale_price_uah": "14800",
            "acquisition_shipping_uah": "150",
            "other_cost_reserve_uah": "250",
            "checked_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    rule = MarketPriceRule.objects.get()
    assert str(rule.expected_final_sale_price_uah) == "14800.00"
    html = admin_client_ru.get("/prices/").content.decode()
    assert "iphone_13" in html


def test_invalid_storage_for_model(admin_client_ru):
    response = admin_client_ru.post(
        "/prices/market/new/",
        {
            "model_key": "iphone_15_pro_max",
            "storage_gb": "128",
            "sim_variant": "ANY",
            "expected_final_sale_price_uah": "30000",
            "acquisition_shipping_uah": "0",
            "other_cost_reserve_uah": "0",
            "checked_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "is_active": "on",
        },
    )
    assert response.status_code == 200
    assert "не существует" in response.content.decode()
    assert MarketPriceRule.objects.count() == 0


def test_create_defect_rule(admin_client_ru):
    response = admin_client_ru.post(
        "/prices/defects/new/",
        {
            "code": "BATTERY_80_84",
            "model_key": "",
            "label": "АКБ 80–84%",
            "amount_uah": "900",
            "exclusive_group": "BATTERY",
            "priority": "200",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    rule = DefectReserveRule.objects.get()
    assert rule.model_key == ""  # universal


def test_stale_badge_shown(admin_client_ru):
    from tests import factories

    factories.create_market_rule(checked_at=timezone.now() - timezone.timedelta(days=30))
    html = admin_client_ru.get("/prices/").content.decode()
    assert "Устарела" in html
