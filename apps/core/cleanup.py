"""Retention cleanup: deletes only technical rows, never business history.

Protected forever: Listing, ListingSnapshot, Evaluation, AiAnalysis,
NotificationOutbox, Deal.
"""

from datetime import timedelta

from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

FAILED_RUN_MIN_RETENTION_DAYS = 180
BATCH_SIZE = 500


def cleanup_counts() -> dict[str, int]:
    """Read-only preview of what run_cleanup(confirm=True) would delete."""
    from axes.models import AccessAttempt, AccessLog
    from apps.core.models import AppState, AuditEvent
    from apps.monitoring.enums import ScanRunStatus
    from apps.monitoring.models import ScanRun

    state = AppState.get_solo()
    now = timezone.now()
    scan_cutoff = now - timedelta(days=state.scan_run_retention_days)
    failed_cutoff = now - timedelta(days=max(state.scan_run_retention_days, FAILED_RUN_MIN_RETENTION_DAYS))
    audit_cutoff = now - timedelta(days=state.audit_retention_days)

    scan_runs = ScanRun.objects.filter(
        status__in=[ScanRunStatus.SUCCESS, ScanRunStatus.PARTIAL], started_at__lt=scan_cutoff
    ).count() + ScanRun.objects.filter(
        status__in=[ScanRunStatus.FAILED, ScanRunStatus.BLOCKED], started_at__lt=failed_cutoff
    ).count()
    audit_events = AuditEvent.objects.filter(created_at__lt=audit_cutoff).count()
    axes_logs = (
        AccessLog.objects.filter(attempt_time__lt=audit_cutoff).count()
        + AccessAttempt.objects.filter(attempt_time__lt=audit_cutoff).count()
    )
    sessions = Session.objects.filter(expire_date__lt=now).count()
    return {
        "scan_runs": scan_runs,
        "audit_events": audit_events,
        "axes_logs": axes_logs,
        "sessions": sessions,
        "would_delete": scan_runs + audit_events + axes_logs + sessions,
    }


def _delete_in_batches(queryset) -> int:
    total = 0
    while True:
        with transaction.atomic():
            batch = list(queryset.values_list("pk", flat=True)[:BATCH_SIZE])
            if not batch:
                break
            deleted, _ = queryset.model.objects.filter(pk__in=batch).delete()
            total += deleted
    return total


def run_cleanup(*, confirm: bool) -> dict[str, int]:
    """Execute retention cleanup. Without confirm=True only returns counts."""
    if not confirm:
        return cleanup_counts()

    from axes.models import AccessAttempt, AccessLog
    from apps.core.models import AppState, AuditEvent
    from apps.monitoring.enums import ScanRunStatus
    from apps.monitoring.models import ScanRun

    state = AppState.get_solo()
    now = timezone.now()
    scan_cutoff = now - timedelta(days=state.scan_run_retention_days)
    failed_cutoff = now - timedelta(days=max(state.scan_run_retention_days, FAILED_RUN_MIN_RETENTION_DAYS))
    audit_cutoff = now - timedelta(days=state.audit_retention_days)

    result = {
        "scan_runs": _delete_in_batches(
            ScanRun.objects.filter(
                status__in=[ScanRunStatus.SUCCESS, ScanRunStatus.PARTIAL],
                started_at__lt=scan_cutoff,
            )
        )
        + _delete_in_batches(
            ScanRun.objects.filter(
                status__in=[ScanRunStatus.FAILED, ScanRunStatus.BLOCKED],
                started_at__lt=failed_cutoff,
            )
        ),
        "audit_events": _delete_in_batches(AuditEvent.objects.filter(created_at__lt=audit_cutoff)),
        "axes_logs": _delete_in_batches(AccessLog.objects.filter(attempt_time__lt=audit_cutoff))
        + _delete_in_batches(AccessAttempt.objects.filter(attempt_time__lt=audit_cutoff)),
        "sessions": _delete_in_batches(Session.objects.filter(expire_date__lt=now)),
    }
    AppState.objects.filter(pk=1).update(last_cleanup_at=now)
    return result
