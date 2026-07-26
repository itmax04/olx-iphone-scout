"""A-12..A-14, A-18/A-19: SearchProfile API."""

import json

import pytest

pytestmark = pytest.mark.django_db

VALID_BODY = {
    "name": "iPhone 13 128 — частные",
    "olx_url": "https://www.olx.ua/uk/list/q-iphone-13/?search%5Border%5D=created_at%3Adesc",
    "is_active": True,
    "target_models": ["iphone_13"],
    "target_storage_gb": [128],
    "min_price_uah": "7000.00",
    "max_purchase_price_uah": "12500.00",
    "min_expected_profit_uah": "1800.00",
    "min_roi_percent": "12.00",
    "private_only": True,
    "delivery_required": False,
    "interval_seconds": 90,
    "jitter_seconds": 15,
    "max_cards": 30,
    "included_keywords": [],
    "excluded_keywords": ["запчастини", "муляж"],
}


def post_json(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json")


def patch_json(client, path, body):
    return client.patch(path, data=json.dumps(body), content_type="application/json")


def test_create_201(admin_client_ru):
    response = post_json(admin_client_ru, "/api/v1/search-profiles/", VALID_BODY)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == VALID_BODY["name"]
    assert data["canonical_url"].startswith("https://www.olx.ua/")
    assert data["min_price_uah"] == "7000.00"  # Decimal строкой


def test_duplicate_409(admin_client_ru):
    post_json(admin_client_ru, "/api/v1/search-profiles/", VALID_BODY)
    response = post_json(admin_client_ru, "/api/v1/search-profiles/", VALID_BODY)
    assert response.status_code == 400 or response.status_code == 409
    # canonical дубликат ловится валидатором формы/сериализатора либо IntegrityError->409


def test_invalid_url_400(admin_client_ru):
    body = dict(VALID_BODY, olx_url="https://example.com/x")
    response = post_json(admin_client_ru, "/api/v1/search-profiles/", body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_field_400(admin_client_ru):
    body = dict(VALID_BODY, hack_field=1)
    response = post_json(admin_client_ru, "/api/v1/search-profiles/", body)
    assert response.status_code == 400
    assert "hack_field" in response.json()["error"]["field_errors"]


def test_interval_bounds_400(admin_client_ru):
    body = dict(VALID_BODY, interval_seconds=30)
    response = post_json(admin_client_ru, "/api/v1/search-profiles/", body)
    assert response.status_code == 400


def test_archive_204_preserves_history(admin_client_ru, market_rule):
    created = post_json(admin_client_ru, "/api/v1/search-profiles/", VALID_BODY).json()["data"]
    from apps.monitoring.collectors.fixture_source import FixtureOlxSource
    from apps.monitoring.models import Listing, SearchProfile
    from apps.monitoring.services import process_profile_scan

    profile = SearchProfile.objects.get(pk=created["id"])
    process_profile_scan(profile, FixtureOlxSource())
    assert Listing.objects.count() == 4

    response = admin_client_ru.delete(f"/api/v1/search-profiles/{profile.pk}/")
    assert response.status_code == 204  # A-14
    assert Listing.objects.count() == 4  # история не удалена
    profile.refresh_from_db()
    assert profile.archived_at is not None


def test_run_conflict_when_monitoring_disabled(admin_client_ru, profile):
    # MONITOR_ENABLED=false в тестах -> effective monitoring выключен -> 409 (A-18)
    response = admin_client_ru.post(f"/api/v1/search-profiles/{profile.pk}/run/")
    assert response.status_code == 409


def test_run_202_when_enabled(admin_client_ru, profile, settings):
    settings.MONITOR_ENABLED = True
    response = admin_client_ru.post(f"/api/v1/search-profiles/{profile.pk}/run/")
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["queued"] is True
    assert data["worker_status"] in ("NEVER_RUN", "HEALTHY", "STALE", "UNAVAILABLE")


def test_run_busy_409(admin_client_ru, profile, settings):
    settings.MONITOR_ENABLED = True
    profile.is_running = True
    profile.save(update_fields=["is_running"])
    response = admin_client_ru.post(f"/api/v1/search-profiles/{profile.pk}/run/")
    assert response.status_code == 409  # A-19


def test_patch_updates(admin_client_ru, profile):
    response = patch_json(
        admin_client_ru,
        f"/api/v1/search-profiles/{profile.pk}/",
        {"interval_seconds": 120, "is_active": False},
    )
    assert response.status_code == 200
    profile.refresh_from_db()
    assert profile.interval_seconds == 120
    assert profile.is_active is False


def test_malformed_uuid_404(admin_client_ru):
    assert admin_client_ru.get("/api/v1/search-profiles/not-a-uuid/").status_code == 404
