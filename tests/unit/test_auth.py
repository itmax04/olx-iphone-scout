"""Auth backend: username/email без учета регистра, fail-closed."""

import pytest
from django.contrib.auth.models import User

from apps.core.authentication import UsernameOrEmailBackend

pytestmark = pytest.mark.django_db

backend = UsernameOrEmailBackend()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="Owner", email="Owner@Example.com", password="secret-password-123"
    )


def test_username_case_insensitive(user):
    assert backend.authenticate(None, username="owner", password="secret-password-123") == user
    assert backend.authenticate(None, username="OWNER", password="secret-password-123") == user


def test_email_case_insensitive(user):
    assert (
        backend.authenticate(None, username="owner@example.com", password="secret-password-123")
        == user
    )


def test_wrong_password(user):
    assert backend.authenticate(None, username="owner", password="wrong") is None


def test_unknown_user():
    assert backend.authenticate(None, username="ghost", password="x") is None


def test_empty_credentials():
    assert backend.authenticate(None, username="", password="") is None


def test_inactive_user_rejected(user):
    user.is_active = False
    user.save()
    assert backend.authenticate(None, username="owner", password="secret-password-123") is None


def test_duplicate_lower_email_impossible(user):
    """Партиальный unique index LOWER(email) исключает неоднозначность."""
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(
            username="second", email="OWNER@example.com", password="secret-password-123"
        )


def test_ambiguous_email_fails_closed(user, monkeypatch):
    """Даже при гипотетически кривых данных backend возвращает None."""

    class FakeQuerySet(list):
        def __getitem__(self, item):
            return list.__getitem__(self, item) if isinstance(item, int) else FakeQuerySet(self)

    def fake_filter(*args, **kwargs):
        return FakeQuerySet([user, user])

    from django.contrib.auth.models import User as UserModel

    monkeypatch.setattr(UserModel.objects, "filter", fake_filter)
    assert (
        backend.authenticate(None, username="owner@example.com", password="secret-password-123")
        is None
    )
