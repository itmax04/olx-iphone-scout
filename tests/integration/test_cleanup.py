"""I-30 / U-39 / F-28: retention-очистка удаляет только разрешенное и старое."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.cleanup import cleanup_counts, run_cleanup
from apps.core.models import AppState, AuditEvent
from apps.monitoring.models import ScanRun
from tests import factories

pytestmark = pytest.mark.django_db


def old_scan_run(days: int, status: str = "SUCCESS") -> ScanRun:
    run = ScanRun.objects.create(status=status)
    ScanRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(days=days))
    return run


def old_audit(days: int) -> AuditEvent:
    event = AuditEvent.objects.create(action="LOGIN_SUCCESS")
    AuditEvent.objects.filter(pk=event.pk).update(created_at=timezone.now() - timedelta(days=days))
    return event


def test_dry_run_counts_only():
    old_scan_run(days=120)
    counts = run_cleanup(confirm=False)
    assert counts["scan_runs"] == 1
    assert ScanRun.objects.count() == 1  # ничего не удалено


def test_confirm_deletes_only_expired():
    expired = old_scan_run(days=120)
    fresh = old_scan_run(days=5)
    failed_recent = old_scan_run(days=120, status="FAILED")  # failed хранится >=180 дней
    failed_old = old_scan_run(days=200, status="FAILED")
    expired_audit = old_audit(days=400)
    fresh_audit = old_audit(days=10)

    result = run_cleanup(confirm=True)

    remaining_runs = set(ScanRun.objects.values_list("pk", flat=True))
    assert expired.pk not in remaining_runs
    assert fresh.pk in remaining_runs
    assert failed_recent.pk in remaining_runs
    assert failed_old.pk not in remaining_runs
    assert not AuditEvent.objects.filter(pk=expired_audit.pk).exists()
    assert AuditEvent.objects.filter(pk=fresh_audit.pk).exists()
    assert result["scan_runs"] == 2
    assert AppState.get_solo().last_cleanup_at is not None


def test_business_data_never_touched():
    listing = factories.create_listing()
    from apps.monitoring.enums import SnapshotSource
    from apps.monitoring.services import record_snapshot

    record_snapshot(listing, SnapshotSource.SEARCH, ["initial"])
    run_cleanup(confirm=True)
    from apps.monitoring.models import Listing, ListingSnapshot

    assert Listing.objects.count() == 1
    assert ListingSnapshot.objects.count() == 1


def test_cleanup_preview_matches():
    old_scan_run(days=120)
    old_audit(days=400)
    counts = cleanup_counts()
    assert (
        counts["would_delete"]
        == counts["scan_runs"] + counts["audit_events"] + counts["axes_logs"] + counts["sessions"]
    )
