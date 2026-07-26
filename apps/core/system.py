"""Safe system status data used by /system/ page and system API endpoints."""

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.core.services import get_app_state, worker_status


def system_status_data() -> dict:
    from apps.alerts.enums import OutboxStatus
    from apps.alerts.models import NotificationOutbox
    from apps.monitoring.enums import ScanRunStatus
    from apps.monitoring.models import ScanRun, SearchProfile

    data: dict = {
        "app_version": settings.APP_VERSION,
        "commit": settings.RENDER_GIT_COMMIT or "local",
        "app_env": settings.APP_ENV,
        "generated_at": timezone.now().isoformat(),
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        data["database"] = "ok"
    except Exception:
        data["database"] = "unavailable"
        return data

    try:
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        data["migrations"] = "current" if not plan else "pending"
    except Exception:
        data["migrations"] = "unknown"

    state = get_app_state()
    data["worker_status"] = worker_status(state)
    data["worker_heartbeat_at"] = (
        state.worker_heartbeat_at.isoformat() if state.worker_heartbeat_at else None
    )
    data["worker_instance"] = state.worker_instance_id or None
    data["monitoring_paused"] = state.monitoring_paused
    data["pause_reason"] = state.pause_reason
    data["safety_block_until"] = (
        state.safety_block_until.isoformat() if state.safety_block_until else None
    )
    data["safety_ack_required"] = state.safety_ack_required
    data["last_cleanup_at"] = state.last_cleanup_at.isoformat() if state.last_cleanup_at else None

    last_success = (
        ScanRun.objects.filter(status=ScanRunStatus.SUCCESS).order_by("-started_at").first()
    )
    data["last_successful_scan_at"] = last_success.started_at.isoformat() if last_success else None
    data["profiles_in_error"] = SearchProfile.objects.filter(
        consecutive_failures__gt=0, archived_at__isnull=True
    ).count()
    data["outbox_pending"] = NotificationOutbox.objects.filter(
        status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY]
    ).count()
    data["outbox_failed"] = NotificationOutbox.objects.filter(status=OutboxStatus.FAILED).count()
    data["openai_configured"] = bool(settings.OPENAI_API_KEY)
    data["telegram_configured"] = bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)
    data["monitor_env_enabled"] = settings.MONITOR_ENABLED
    data["ai_env_enabled"] = settings.AI_ENABLED

    from apps.core.models import AuditEvent

    data["recent_audit"] = [
        {
            "action": event.action,
            "target_type": event.target_type,
            "created_at": event.created_at.isoformat(),
        }
        for event in AuditEvent.objects.order_by("-created_at")[:10]
    ]
    return data
