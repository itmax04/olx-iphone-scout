"""A-27 и Deal API: снапшот, серверная прибыль, optimistic locking."""

import json

import pytest
from django.utils import timezone

from tests import factories

pytestmark = pytest.mark.django_db


def post_json(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json")


def patch_json(client, path, body):
    return client.patch(path, data=json.dumps(body), content_type="application/json")


@pytest.fixture
def bought(admin_client_ru):
    listing = factories.create_listing(decision_status="CONTACTED")
    response = post_json(
        admin_client_ru,
        "/api/v1/deals/",
        {
            "listing_id": str(listing.pk),
            "purchase_price_uah": "11500.00",
            "purchased_at": timezone.now().isoformat(),
            "acquisition_shipping_uah": "100.00",
            "repair_cost_uah": "500.00",
            "other_cost_uah": "100.00",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_create_deal_snapshot(bought):
    assert bought["status"] == "IN_STOCK"
    assert bought["realized_profit_uah"] is None
    assert bought["purchase_snapshot"]["title"] == "iPhone 13 128GB Midnight"
    assert bought["listing_status_before_purchase"] == "CONTACTED"


def test_duplicate_deal_409(admin_client_ru, bought):
    response = post_json(
        admin_client_ru,
        "/api/v1/deals/",
        {"listing_id": bought["listing_id"], "purchase_price_uah": "10000.00"},
    )
    assert response.status_code == 409


def test_sold_server_profit(admin_client_ru, bought):
    response = patch_json(
        admin_client_ru,
        f"/api/v1/deals/{bought['id']}/",
        {
            "status": "SOLD",
            "sale_price_uah": "14500.00",
            "sold_at": timezone.now().isoformat(),
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["realized_profit_uah"] == "2300.00"


def test_client_cannot_set_realized_profit(admin_client_ru, bought):
    response = patch_json(
        admin_client_ru,
        f"/api/v1/deals/{bought['id']}/",
        {"realized_profit_uah": "999999.00"},
    )
    assert response.status_code == 400  # unknown field


def test_stale_updated_at_409(admin_client_ru, bought):
    response = patch_json(
        admin_client_ru,
        f"/api/v1/deals/{bought['id']}/",
        {"repair_cost_uah": "600.00", "expected_updated_at": "2000-01-01T00:00:00"},
    )
    assert response.status_code == 409


def test_csv_export_bom_and_injection(admin_client_ru, bought):
    from apps.deals.models import Deal

    deal = Deal.objects.get(pk=bought["id"])
    deal.notes = "=HYPERLINK(evil)"
    deal.save(update_fields=["notes"])
    response = admin_client_ru.get("/api/v1/deals/export.csv")
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert content.startswith("﻿")  # UTF-8 BOM (A-27)
    assert "'=HYPERLINK" in content  # U-40: formula injection нейтрализована
    assert "text/csv" in response["Content-Type"]


def test_invalid_status_filter_400(admin_client_ru):
    assert admin_client_ru.get("/api/v1/deals/?status=hack").status_code == 400
