"""S-17 и контроль доступа: HTML redirect, API 403, inactive user."""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

API_PATHS = [
    "/api/v1/listings/",
    "/api/v1/search-profiles/",
    "/api/v1/market-price-rules/",
    "/api/v1/defect-reserve-rules/",
    "/api/v1/deals/",
    "/api/v1/scan-runs/",
    "/api/v1/settings/",
    "/api/v1/system/status/",
    "/api/v1/dashboard/stats/",
    "/api/v1/system/diagnostic/",
]


@pytest.mark.parametrize("path", API_PATHS)
def test_anonymous_api_403(client, path):
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["error"]["code"] in ("AUTH_REQUIRED", "PERMISSION_DENIED")


@pytest.mark.parametrize("path", API_PATHS)
def test_regular_user_api_403(regular_user, path):
    client = Client()
    client.force_login(regular_user)
    assert client.get(path).status_code == 403


def test_inactive_superuser_denied(admin_user):
    admin_user.is_active = False
    admin_user.save()
    client = Client()
    response = client.post(
        "/accounts/login/", {"identifier": "owner", "password": "test-password-12345"}
    )
    assert response.status_code == 200  # форма с ошибкой, входа нет (S-17)
    assert client.get("/dashboard/").status_code == 302


def test_admin_panel_requires_superuser(regular_user):
    client = Client()
    client.force_login(regular_user)
    response = client.get("/admin/")
    assert response.status_code == 302  # редирект на admin login, не контент


def test_no_public_signup():
    for path in ("/accounts/signup/", "/accounts/register/", "/api/v1/auth/register/"):
        assert Client().get(path).status_code == 404
