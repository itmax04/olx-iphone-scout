from django.contrib import admin

from apps.core.models import AppState, AuditEvent


@admin.register(AppState)
class AppStateAdmin(admin.ModelAdmin):
    list_display = ("id", "monitoring_paused", "worker_heartbeat_at", "ai_enabled", "updated_at")

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "target_type", "target_id")
    list_filter = ("action",)
    readonly_fields = (
        "id",
        "actor",
        "action",
        "target_type",
        "target_id",
        "changes",
        "request_id",
        "ip_hash",
        "created_at",
    )
    actions = None

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
