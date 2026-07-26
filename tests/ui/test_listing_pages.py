"""E-08/E-09: списки и карточка объявления с данными fixture pipeline."""

import pytest
from django.core.management import call_command

from apps.monitoring.models import Listing

pytestmark = pytest.mark.django_db


@pytest.fixture
def pipeline(db):
    call_command("run_fixture_pipeline", stdout=open("/dev/null", "w"))
    return Listing.objects.get(olx_id="800000001")


def test_listing_list_shows_candidate(admin_client_ru, pipeline):
    html = admin_client_ru.get("/listings/?candidate=1").content.decode()
    assert "iPhone 13 128GB Midnight" in html
    assert "2 400" in html or "2400" in html


def test_listing_detail_economics(admin_client_ru, pipeline):
    html = admin_client_ru.get(f"/listings/{pipeline.pk}/").content.decode()
    assert "Экономика" in html
    assert "14 800" in html or "14800" in html  # ожидаемая продажа
    assert "PROFIT_THRESHOLD_MET" in html
    assert "История изменений" in html
    assert "Открыть OLX" in html


def test_listing_detail_status_form(admin_client_ru, pipeline):
    response = admin_client_ru.post(
        f"/listings/{pipeline.pk}/status/",
        {"status": "CONTACTED", "note": "Написал", "expected_current_status": "CANDIDATE"},
    )
    assert response.status_code == 302
    pipeline.refresh_from_db()
    assert pipeline.decision_status == "CONTACTED"  # E-10 аналог


def test_filters_no_match_empty_state(admin_client_ru, pipeline):
    html = admin_client_ru.get("/listings/?model=iphone_11").content.decode()
    assert "Ничего не соответствует фильтрам" in html


def test_runs_page_shows_run(admin_client_ru, pipeline):
    html = admin_client_ru.get("/runs/").content.decode()
    assert "Успех" in html
