"""S-02/S-09/S-18: заголовки безопасности и продакшен-конфигурация."""

import pytest

pytestmark = pytest.mark.django_db


def test_csp_header_present_no_unsafe_inline(admin_client_ru):
    response = admin_client_ru.get("/dashboard/")
    csp = response.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "unsafe-inline" not in csp  # S-09
    assert "frame-ancestors 'none'" in csp


def test_nosniff_and_frame_deny(admin_client_ru):
    response = admin_client_ru.get("/dashboard/")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "same-origin"


def test_request_id_header(admin_client_ru):
    response = admin_client_ru.get("/dashboard/")
    assert len(response.headers.get("X-Request-ID", "")) == 36  # A-28


def test_host_header_attack_400(admin_client_ru):
    response = admin_client_ru.get("/dashboard/", HTTP_HOST="evil.example.com")
    assert response.status_code == 400  # S-08


def test_base_password_hashers_argon2_first():
    # test.py подменяет хешеры для скорости; проверяем боевую конфигурацию base.
    import importlib

    base = importlib.import_module("config.settings.base")
    assert base.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")  # S-01


def test_argon2_hash_in_db(admin_user, settings):
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.Argon2PasswordHasher",
    ]
    admin_user.set_password("check-argon2-hash-123")
    admin_user.save()
    admin_user.refresh_from_db()
    assert admin_user.password.startswith("argon2")
    assert "check-argon2-hash-123" not in admin_user.password


def test_error_pages_no_traceback(admin_client_ru):
    response = admin_client_ru.get("/definitely-not-a-page/")
    assert response.status_code == 404
    assert "Traceback" not in response.content.decode()  # S-18
