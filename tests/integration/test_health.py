"""F-27: live/ready health endpoints."""

import pytest
from django.test import Client

from apps.core.models import AppState

pytestmark = pytest.mark.django_db


def test_live_ok_without_auth():
    response = Client().get("/api/v1/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "web"}


def test_ready_ok_with_appstate():
    AppState.get_solo()
    response = Client().get("/api/v1/health/ready/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["schema"] == "current"


def test_ready_503_without_appstate():
    AppState.objects.all().delete()
    response = Client().get("/api/v1/health/ready/")
    assert response.status_code == 503
    assert response.json()["database"] == "app_state_missing"


def test_health_reveals_no_secrets():
    response = Client().get("/api/v1/health/ready/")
    text = response.content.decode()
    for needle in ("postgresql://", "SECRET", "token", "password"):
        assert needle not in text
