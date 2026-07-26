"""Shared pytest fixtures. Tests never call OLX, OpenAI or Telegram."""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from tests import factories


@pytest.fixture
def admin_user(db) -> User:
    return User.objects.create_superuser(
        username="owner", email="owner@example.com", password="test-password-12345"
    )


@pytest.fixture
def regular_user(db) -> User:
    return User.objects.create_user(
        username="mortal", email="mortal@example.com", password="test-password-12345"
    )


@pytest.fixture
def admin_client_ru(admin_user) -> Client:
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def profile(db):
    return factories.create_profile()


@pytest.fixture
def market_rule(db):
    return factories.create_market_rule()


@pytest.fixture
def listing(db):
    return factories.create_listing()


@pytest.fixture
def fixture_source():
    from apps.monitoring.collectors.fixture_source import FixtureOlxSource

    return FixtureOlxSource()
