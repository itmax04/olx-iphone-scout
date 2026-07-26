"""E2E: логин → создать поиск и цену → fixture-скан → кандидат в UI.

Полный стек через Django test client + fixture collector (без живого браузера
и внешней сети — см. docs/ARCHITECTURE_DECISIONS.md).
"""

import pytest
from django.test import Client
from django.utils import timezone

from apps.monitoring.collectors.fixture_source import FixtureOlxSource
from apps.monitoring.models import SearchProfile
from apps.monitoring.services import process_profile_scan

pytestmark = pytest.mark.django_db


def test_full_search_flow(admin_user):
    client = Client()
    # 1. Вход
    response = client.post(
        "/accounts/login/", {"identifier": "owner", "password": "test-password-12345"}
    )
    assert response.status_code == 302

    # 2. Создание рыночной цены
    response = client.post(
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

    # 2b. Резерв дефекта для заявленной АКБ 85–89%
    response = client.post(
        "/prices/defects/new/",
        {
            "code": "BATTERY_85_89",
            "model_key": "",
            "label": "АКБ 85–89%",
            "amount_uah": "500",
            "exclusive_group": "BATTERY",
            "priority": "100",
            "is_active": "on",
        },
    )
    assert response.status_code == 302

    # 3. Создание поискового профиля
    response = client.post(
        "/searches/new/",
        {
            "name": "Мой первый поиск",
            "olx_url": "https://www.olx.ua/uk/list/q-iphone-13/",
            "is_active": "on",
            "target_models": ["iphone_13"],
            "target_storage_gb": ["128"],
            "min_price_uah": "3000",
            "max_purchase_price_uah": "12500",
            "min_expected_profit_uah": "1800",
            "min_roi_percent": "12.00",
            "private_only": "on",
            "interval_seconds": "90",
            "jitter_seconds": "15",
            "max_cards": "30",
            "included_keywords": "",
            "excluded_keywords": "",
        },
    )
    assert response.status_code == 302
    profile = SearchProfile.objects.get(name="Мой первый поиск")

    # 4. Скан (worker-путь) на fixtures
    run = process_profile_scan(profile, FixtureOlxSource())
    assert run.status == "SUCCESS"

    # 5. Кандидат виден в списке и на дашборде
    html = client.get("/listings/?candidate=1").content.decode()
    assert "iPhone 13 128GB Midnight" in html
    dashboard = client.get("/dashboard/").content.decode()
    assert "iPhone 13 128GB Midnight" in dashboard
