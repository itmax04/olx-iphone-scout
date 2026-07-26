"""I-04 / F-02: идемпотентный bootstrap администратора."""

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db

ENV = {
    "ADMIN_USERNAME": "owner",
    "ADMIN_EMAIL": "owner@example.com",
    "ADMIN_PASSWORD": "strong-admin-password-42",
}


def run(monkeypatch, **overrides):
    env = {**ENV, **overrides}
    for key in ("ADMIN_USERNAME", "ADMIN_EMAIL", "ADMIN_PASSWORD"):
        if env.get(key) is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, env[key])
    call_command("bootstrap_admin")


def test_creates_superuser(monkeypatch):
    run(monkeypatch)
    user = User.objects.get(username="owner")
    assert user.is_superuser and user.is_staff and user.is_active
    assert user.check_password("strong-admin-password-42")


def test_repeat_run_keeps_password(monkeypatch):
    run(monkeypatch)
    run(monkeypatch, ADMIN_PASSWORD="another-password-should-be-ignored-99")
    user = User.objects.get(username="owner")
    assert user.check_password("strong-admin-password-42")  # пароль не сброшен
    assert User.objects.filter(is_superuser=True).count() == 1


def test_missing_env_fails_on_first_run(monkeypatch):
    with pytest.raises(CommandError):
        run(monkeypatch, ADMIN_PASSWORD=None)


def test_weak_password_rejected(monkeypatch):
    with pytest.raises(CommandError):
        run(monkeypatch, ADMIN_PASSWORD="short")


def test_missing_env_ok_when_admin_exists(monkeypatch):
    run(monkeypatch)
    # После создания admin переменные можно удалить: команда просто отчитывается.
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    call_command("bootstrap_admin")  # не бросает
