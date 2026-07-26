"""A-08..A-11, F-20..F-22: Listings API."""

import json

import pytest

from tests import factories

pytestmark = pytest.mark.django_db


def patch_json(client, path, body):
    return client.patch(path, data=json.dumps(body), content_type="application/json")


class TestList:
    def test_filters_exact(self, admin_client_ru):
        factories.create_listing(model_key="iphone_13", current_is_candidate=True)
        factories.create_listing(model_key="iphone_14", title="iPhone 14 128GB")
        response = admin_client_ru.get("/api/v1/listings/?model=iphone_13&candidate=true")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 1  # A-10
        assert body["data"][0]["model_key"] == "iphone_13"

    def test_unknown_sort_400(self, admin_client_ru):
        assert admin_client_ru.get("/api/v1/listings/?sort=hack").status_code == 400  # A-11

    def test_page_size_capped(self, admin_client_ru):
        assert admin_client_ru.get("/api/v1/listings/?page_size=1000").status_code == 400  # A-09

    def test_pagination_meta(self, admin_client_ru):
        for _ in range(3):
            factories.create_listing()
        body = admin_client_ru.get("/api/v1/listings/?page_size=2").json()
        assert body["meta"] == {"page": 1, "page_size": 2, "total": 3, "pages": 2}

    def test_description_not_in_list(self, admin_client_ru, listing):
        body = admin_client_ru.get("/api/v1/listings/").json()
        assert "description" not in body["data"][0]


class TestDetail:
    def test_detail_includes_history(self, admin_client_ru, market_rule):
        listing = factories.create_listing(title="iPhone 13 128GB", description="")
        from apps.monitoring.enums import SnapshotSource
        from apps.monitoring.models import ListingDiscovery
        from apps.monitoring.services import evaluate_listing, record_snapshot

        profile = factories.create_profile()
        ListingDiscovery.objects.create(listing=listing, search_profile=profile)
        record_snapshot(listing, SnapshotSource.SEARCH, ["initial"])
        evaluate_listing(listing)
        response = admin_client_ru.get(f"/api/v1/listings/{listing.pk}/")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["current_evaluation"]["decision"] == "CANDIDATE"
        assert data["source_search_profile"] == str(profile.pk)
        assert len(data["snapshots"]) == 1
        assert len(data["evaluations"]) == 1

    def test_malformed_uuid_404_not_500(self, admin_client_ru):
        assert admin_client_ru.get("/api/v1/listings/xx-yy/").status_code == 404  # A-08


class TestStatus:
    def test_valid_transition(self, admin_client_ru, listing):
        response = patch_json(
            admin_client_ru,
            f"/api/v1/listings/{listing.pk}/status/",
            {"status": "CONTACTED", "note": "Написал продавцу", "expected_current_status": "NEW"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["decision_status"] == "CONTACTED"

    def test_invalid_transition_409(self, admin_client_ru):
        listing = factories.create_listing(decision_status="SOLD")
        response = patch_json(
            admin_client_ru, f"/api/v1/listings/{listing.pk}/status/", {"status": "NEW"}
        )
        assert response.status_code == 409

    def test_stale_expected_409(self, admin_client_ru, listing):
        response = patch_json(
            admin_client_ru,
            f"/api/v1/listings/{listing.pk}/status/",
            {"status": "REVIEWED", "expected_current_status": "CANDIDATE"},
        )
        assert response.status_code == 409

    def test_note_only_patch(self, admin_client_ru, listing):
        response = patch_json(
            admin_client_ru, f"/api/v1/listings/{listing.pk}/status/", {"note": "Уточнить АКБ"}
        )
        assert response.status_code == 200
        listing.refresh_from_db()
        assert listing.manual_notes == "Уточнить АКБ"

    def test_unknown_field_400(self, admin_client_ru, listing):
        response = patch_json(
            admin_client_ru, f"/api/v1/listings/{listing.pk}/status/", {"hack": 1}
        )
        assert response.status_code == 400


class TestReanalyze:
    def test_ai_disabled_422(self, admin_client_ru, listing):
        response = admin_client_ru.post(f"/api/v1/listings/{listing.pk}/reanalyze/")
        assert response.status_code == 422  # AI выключен в тестах

    def test_inactive_listing_409(self, admin_client_ru, settings, admin_user):
        settings.AI_ENABLED = True
        settings.OPENAI_API_KEY = "sk-test-not-real"
        from apps.core.models import AppState

        state = AppState.get_solo()
        state.ai_enabled = True
        state.save()
        listing = factories.create_listing(is_active=False)
        response = admin_client_ru.post(f"/api/v1/listings/{listing.pk}/reanalyze/")
        assert response.status_code == 409

    def test_queue_202(self, admin_client_ru, settings, listing):
        settings.AI_ENABLED = True
        settings.OPENAI_API_KEY = "sk-test-not-real"
        from apps.core.models import AppState

        state = AppState.get_solo()
        state.ai_enabled = True
        state.save()
        response = admin_client_ru.post(f"/api/v1/listings/{listing.pk}/reanalyze/")
        assert response.status_code == 202
        data = response.json()["data"]
        assert data["queued"] is True
        assert data["analysis_status"] == "PENDING"
        # повторный запрос при уже выполняющемся анализе -> 409
        second = admin_client_ru.post(f"/api/v1/listings/{listing.pk}/reanalyze/")
        assert second.status_code == 409
