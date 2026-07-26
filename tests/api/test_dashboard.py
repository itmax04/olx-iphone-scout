"""A-25/F-25: dashboard stats — честные нули на пустой БД."""

import pytest

pytestmark = pytest.mark.django_db


def test_empty_db_zeros(admin_client_ru):
    response = admin_client_ru.get("/api/v1/dashboard/stats/")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["new_listings"] == 0
    assert data["candidates"] == 0
    assert data["price_drops"] == 0
    assert data["candidate_expected_profit_uah"] == "0"
    assert data["capital_in_stock_uah"] == "0"
    assert data["realized_profit_uah"] == "0"
    assert data["worker_status"] == "NEVER_RUN"


def test_invalid_period_400(admin_client_ru):
    assert admin_client_ru.get("/api/v1/dashboard/stats/?period=year").status_code == 400


def test_stats_with_data(admin_client_ru, market_rule):
    from apps.monitoring.collectors.fixture_source import FixtureOlxSource
    from apps.monitoring.services import process_profile_scan
    from tests import factories

    factories.create_defect_rule()  # резерв для АКБ 85–89% из описания фикстуры
    profile = factories.create_profile()
    process_profile_scan(profile, FixtureOlxSource())
    data = admin_client_ru.get("/api/v1/dashboard/stats/").json()["data"]
    assert data["new_listings"] == 4
    assert data["candidates"] == 1
    assert data["candidate_expected_profit_uah"] == "2400.00"
