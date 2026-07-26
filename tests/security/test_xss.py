"""S-04: XSS из OLX title/description отображается как текст."""

import pytest

from tests import factories

pytestmark = pytest.mark.django_db

PAYLOAD = '<script>alert("xss")</script>'


def test_title_escaped_in_list(admin_client_ru):
    factories.create_listing(title=f"iPhone 13 {PAYLOAD}", description="")
    html = admin_client_ru.get("/listings/").content.decode()
    assert PAYLOAD not in html
    assert "&lt;script&gt;" in html


def test_description_escaped_in_detail(admin_client_ru):
    listing = factories.create_listing(description=f"Описание {PAYLOAD}")
    html = admin_client_ru.get(f"/listings/{listing.pk}/").content.decode()
    assert PAYLOAD not in html
    assert "&lt;script&gt;" in html


def test_notes_escaped(admin_client_ru):
    listing = factories.create_listing(manual_notes=PAYLOAD)
    html = admin_client_ru.get(f"/listings/{listing.pk}/").content.decode()
    assert PAYLOAD not in html


def test_sql_injection_in_filter_safe(admin_client_ru):
    factories.create_listing()
    response = admin_client_ru.get("/api/v1/listings/?q=' OR 1=1;--")
    assert response.status_code == 200  # S-05: параметризация ORM
    assert response.json()["meta"]["total"] == 0
