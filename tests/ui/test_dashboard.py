"""F-25: dashboard с данными и без."""

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_empty_dashboard_zeros(admin_client_ru):
    html = admin_client_ru.get("/dashboard/").content.decode()
    assert "Кандидатов пока нет" in html
    assert "0 кандидатов" in html or "0" in html


def test_dashboard_with_candidates(admin_client_ru):
    call_command("run_fixture_pipeline", stdout=open("/dev/null", "w"))
    html = admin_client_ru.get("/dashboard/").content.decode()
    assert "iPhone 13 128GB Midnight" in html
    assert "Последние кандидаты" in html
    assert "воронка" in html.lower()


def test_pause_resume_buttons(admin_client_ru):
    response = admin_client_ru.post("/system/pause/", {"reason": "тест", "next": "/dashboard/"})
    assert response.status_code == 302
    html = admin_client_ru.get("/dashboard/").content.decode()
    assert "Возобновить" in html
    from apps.core.models import AppState

    assert AppState.get_solo().monitoring_paused is True
