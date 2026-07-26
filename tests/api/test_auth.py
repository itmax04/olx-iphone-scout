"""A-01, A-02, A-30: доступ к API."""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_anonymous_me_403_json():
    response = Client().get("/api/v1/auth/me/")
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "AUTH_REQUIRED"
    assert "request_id" in body["error"]


def test_anonymous_write_403():
    response = Client().post("/api/v1/system/pause/", data="{}", content_type="application/json")
    assert response.status_code == 403


def test_regular_user_403(regular_user):
    client = Client()
    client.force_login(regular_user)
    for path in ("/api/v1/auth/me/", "/api/v1/listings/", "/api/v1/settings/"):
        assert client.get(path).status_code == 403  # A-30


def test_staff_without_superuser_403(regular_user):
    regular_user.is_staff = True
    regular_user.save()
    client = Client()
    client.force_login(regular_user)
    assert client.get("/api/v1/listings/").status_code == 403


def test_admin_me_ok(admin_client_ru):
    response = admin_client_ru.get("/api/v1/auth/me/")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {"username": "owner", "email": "owner@example.com", "role": "Administrator"}


def test_invalid_verb_405(admin_client_ru):
    response = admin_client_ru.delete("/api/v1/auth/me/")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
