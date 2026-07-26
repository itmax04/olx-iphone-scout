"""E-05/E-06: создание поиска через HTML-форму."""

import pytest

from apps.monitoring.models import SearchProfile

pytestmark = pytest.mark.django_db

FORM = {
    "name": "iPhone 13 частные",
    "olx_url": "https://www.olx.ua/uk/list/q-iphone-13/?search%5Border%5D=created_at%3Adesc",
    "is_active": "on",
    "target_models": ["iphone_13"],
    "target_storage_gb": ["128"],
    "min_price_uah": "7000",
    "max_purchase_price_uah": "12500",
    "min_expected_profit_uah": "1800",
    "min_roi_percent": "12.00",
    "private_only": "on",
    "interval_seconds": "90",
    "jitter_seconds": "15",
    "max_cards": "30",
    "included_keywords": "",
    "excluded_keywords": "запчастини, муляж",
}


def test_create_profile_via_form(admin_client_ru):
    response = admin_client_ru.post("/searches/new/", FORM)
    assert response.status_code == 302
    profile = SearchProfile.objects.get()
    assert profile.name == "iPhone 13 частные"
    assert profile.excluded_keywords == ["запчастини", "муляж"]
    assert profile.canonical_url.startswith("https://www.olx.ua/")
    html = admin_client_ru.get("/searches/").content.decode()
    assert "iPhone 13 частные" in html  # E-05


def test_invalid_price_inline_error(admin_client_ru):
    bad = dict(FORM, max_purchase_price_uah="100", min_price_uah="7000")
    response = admin_client_ru.post("/searches/new/", bad)
    assert response.status_code == 200  # форма с ошибкой
    assert "больше минимальной цены" in response.content.decode()  # E-06
    assert SearchProfile.objects.count() == 0


def test_duplicate_url_error(admin_client_ru):
    admin_client_ru.post("/searches/new/", FORM)
    response = admin_client_ru.post("/searches/new/", dict(FORM, name="Другое имя"))
    assert response.status_code == 200
    assert "уже существует" in response.content.decode()
    assert SearchProfile.objects.count() == 1


def test_edit_form_prefilled(admin_client_ru):
    admin_client_ru.post("/searches/new/", FORM)
    profile = SearchProfile.objects.get()
    html = admin_client_ru.get(f"/searches/{profile.pk}/edit/").content.decode()
    assert "iPhone 13 частные" in html
    assert "запчастини" in html


def test_archive_flow(admin_client_ru):
    admin_client_ru.post("/searches/new/", FORM)
    profile = SearchProfile.objects.get()
    response = admin_client_ru.post(f"/searches/{profile.pk}/archive/")
    assert response.status_code == 302
    profile.refresh_from_db()
    assert profile.archived_at is not None
