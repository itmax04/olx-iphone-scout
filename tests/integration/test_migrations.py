"""I-01/I-02: миграции применяются с нуля и без дрейфа."""

import io

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.core.models import AppState

pytestmark = pytest.mark.django_db


def test_no_pending_migrations():
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    assert plan == []  # I-01: тестовая БД создана полным прогоном миграций


def test_no_model_drift():
    out = io.StringIO()
    call_command("makemigrations", "--check", "--dry-run", stdout=out)
    # exit 0 означает отсутствие дрейфа; assert не нужен, команда бросит SystemExit


def test_appstate_singleton_seeded():
    state = AppState.get_solo()
    assert state.pk == 1
    assert state.market_price_stale_days == 7


def test_lower_email_unique_index_exists():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE indexname = 'auth_user_email_lower_uniq'"
        )
        assert cursor.fetchone() is not None


def test_duplicate_lower_email_rejected():
    from django.contrib.auth.models import User
    from django.db import IntegrityError, transaction

    User.objects.create_user(username="a", email="Same@Example.com", password="x-password-123")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(username="b", email="same@example.com", password="x-password-123")
