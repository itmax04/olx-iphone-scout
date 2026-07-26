"""S-03: CSRF обязателен для state-changing запросов."""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def strict_client(admin_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    return client


def test_html_post_without_csrf_403(strict_client, listing):
    response = strict_client.post(f"/listings/{listing.pk}/status/", {"status": "REVIEWED"})
    assert response.status_code == 403


def test_api_post_without_csrf_403(strict_client):
    response = strict_client.post(
        "/api/v1/system/pause/", data='{"reason": "x"}', content_type="application/json"
    )
    assert response.status_code == 403


def test_api_patch_without_csrf_403(strict_client):
    response = strict_client.patch(
        "/api/v1/settings/",
        data='{"market_price_stale_days": 5}',
        content_type="application/json",
    )
    assert response.status_code == 403


def test_post_with_csrf_token_ok(admin_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    page = client.get("/settings/")
    token = page.context["csrf_token"]
    response = client.post("/system/pause/", {"reason": "x", "csrfmiddlewaretoken": token})
    assert response.status_code == 302
