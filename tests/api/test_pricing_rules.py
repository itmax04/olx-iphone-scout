"""A-16/A-17: pricing API."""

import json

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db

MARKET_BODY = {
    "model_key": "iphone_13",
    "storage_gb": 128,
    "sim_variant": "ANY",
    "expected_final_sale_price_uah": "14800.00",
    "acquisition_shipping_uah": "150.00",
    "other_cost_reserve_uah": "250.00",
    "checked_at": "2026-07-24T10:00:00Z",
    "is_active": True,
}

DEFECT_BODY = {
    "code": "BATTERY_80_84",
    "model_key": "iphone_13",
    "label": "АКБ 80–84%",
    "amount_uah": "900.00",
    "exclusive_group": "BATTERY",
    "priority": 200,
    "is_active": True,
}


def post_json(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json")


class TestMarketRules:
    def test_create_decimal_as_string(self, admin_client_ru):
        response = post_json(admin_client_ru, "/api/v1/market-price-rules/", MARKET_BODY)
        assert response.status_code == 201
        assert response.json()["data"]["expected_final_sale_price_uah"] == "14800.00"  # A-16

    def test_duplicate_409(self, admin_client_ru):
        post_json(admin_client_ru, "/api/v1/market-price-rules/", MARKET_BODY)
        response = post_json(admin_client_ru, "/api/v1/market-price-rules/", MARKET_BODY)
        assert response.status_code == 409  # A-17

    def test_invalid_storage_for_model_400(self, admin_client_ru):
        body = dict(MARKET_BODY, model_key="iphone_15_pro_max", storage_gb=128)
        response = post_json(admin_client_ru, "/api/v1/market-price-rules/", body)
        assert response.status_code == 400

    def test_future_checked_at_400(self, admin_client_ru):
        future = (timezone.now() + timezone.timedelta(days=1)).isoformat()
        response = post_json(
            admin_client_ru, "/api/v1/market-price-rules/", dict(MARKET_BODY, checked_at=future)
        )
        assert response.status_code == 400

    def test_deactivate_204(self, admin_client_ru):
        rule_id = post_json(admin_client_ru, "/api/v1/market-price-rules/", MARKET_BODY).json()[
            "data"
        ]["id"]
        response = admin_client_ru.delete(f"/api/v1/market-price-rules/{rule_id}/")
        assert response.status_code == 204
        from apps.pricing.models import MarketPriceRule

        assert MarketPriceRule.objects.get(pk=rule_id).is_active is False

    def test_negative_amount_400(self, admin_client_ru):
        response = post_json(
            admin_client_ru,
            "/api/v1/market-price-rules/",
            dict(MARKET_BODY, acquisition_shipping_uah="-5.00"),
        )
        assert response.status_code == 400


class TestDefectRules:
    def test_create_201(self, admin_client_ru):
        response = post_json(admin_client_ru, "/api/v1/defect-reserve-rules/", DEFECT_BODY)
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["code"] == "BATTERY_80_84"
        assert data["amount_uah"] == "900.00"

    def test_code_outside_allowlist_400(self, admin_client_ru):
        response = post_json(
            admin_client_ru, "/api/v1/defect-reserve-rules/", dict(DEFECT_BODY, code="EXPLODED")
        )
        assert response.status_code == 400

    def test_duplicate_code_model_409(self, admin_client_ru):
        post_json(admin_client_ru, "/api/v1/defect-reserve-rules/", DEFECT_BODY)
        response = post_json(admin_client_ru, "/api/v1/defect-reserve-rules/", DEFECT_BODY)
        assert response.status_code == 409

    def test_unknown_field_400(self, admin_client_ru):
        response = post_json(
            admin_client_ru, "/api/v1/defect-reserve-rules/", dict(DEFECT_BODY, hack=1)
        )
        assert response.status_code == 400
