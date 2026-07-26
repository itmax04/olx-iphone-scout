"""E-01..E-03: страницы входа и блокировка перебора."""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_login_page_renders(client):
    response = client.get("/accounts/login/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "Логин или email" in html
    assert "Запомнить" in html


def test_wrong_password_neutral_error(client, admin_user):
    response = client.post(
        "/accounts/login/", {"identifier": "owner", "password": "wrong-password"}
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "Неверный логин или пароль" in html
    assert "owner" not in html.split("Неверный")[1][:200]  # не раскрывает существование


def test_successful_login_redirects(client, admin_user):
    response = client.post(
        "/accounts/login/", {"identifier": "owner", "password": "test-password-12345"}
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard/"


def test_lockout_after_five_failures(admin_user):
    client = Client()
    for _ in range(5):
        client.post("/accounts/login/", {"identifier": "owner", "password": "bad"})
    response = client.post(
        "/accounts/login/", {"identifier": "owner", "password": "test-password-12345"}
    )
    assert response.status_code == 429  # E-03: axes lockout


def test_unsafe_next_ignored(client, admin_user):
    response = client.post(
        "/accounts/login/",
        {
            "identifier": "owner",
            "password": "test-password-12345",
            "next": "https://evil.example.com/",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard/"  # S-07


def test_logout_invalidates_session(admin_client_ru):
    assert admin_client_ru.get("/dashboard/").status_code == 200
    response = admin_client_ru.post("/accounts/logout/")
    assert response.status_code == 302
    assert admin_client_ru.get("/dashboard/").status_code == 302  # E-20


def test_password_change_keeps_session(admin_client_ru, admin_user):
    response = admin_client_ru.post(
        "/accounts/password_change/",
        {
            "old_password": "test-password-12345",
            "new_password1": "new-strong-password-777",
            "new_password2": "new-strong-password-777",
        },
    )
    assert response.status_code == 302
    assert admin_client_ru.get("/dashboard/").status_code == 200  # E-04
