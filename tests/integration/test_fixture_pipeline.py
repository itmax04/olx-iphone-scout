"""I-03: run_fixture_pipeline идемпотентна и защищена от production."""

import io

import pytest
from django.core.management import CommandError, call_command

from apps.alerts.models import NotificationOutbox
from apps.analysis.models import Evaluation
from apps.monitoring.models import Listing

pytestmark = pytest.mark.django_db


def run_pipeline(*args) -> str:
    out = io.StringIO()
    call_command("run_fixture_pipeline", *args, stdout=out)
    return out.getvalue()


def test_pipeline_pass_and_idempotent():
    first = run_pipeline()
    assert "FIXTURE_PIPELINE=PASS" in first
    listings = Listing.objects.count()
    evaluations = Evaluation.objects.count()
    outbox = NotificationOutbox.objects.count()
    assert listings == 4
    assert outbox == 1  # один кандидат -> один alert

    second = run_pipeline()
    assert "FIXTURE_PIPELINE=PASS" in second
    assert Listing.objects.count() == listings  # I-03: без дублей
    assert Evaluation.objects.count() == evaluations
    assert NotificationOutbox.objects.count() == outbox


def test_price_drop_pass():
    run_pipeline()
    run_pipeline("--price-drop")
    listing = Listing.objects.get(olx_id="800000001")
    assert str(listing.current_price_uah) == "10400.00"
    assert NotificationOutbox.objects.filter(event_type="PRICE_DROP").count() == 1


def test_collector_only_stops_early():
    output = run_pipeline("--collector-only")
    assert "collector-only" in output


def test_production_guard(settings):
    settings.APP_ENV = "production"
    with pytest.raises(CommandError):
        run_pipeline()


def test_monitor_enabled_guard(settings):
    settings.MONITOR_ENABLED = True
    with pytest.raises(CommandError):
        run_pipeline()


def test_cleanup_namespace():
    run_pipeline()
    output = run_pipeline("--cleanup-fixture-namespace")
    assert "cleanup" in output
    assert Listing.objects.count() == 0
