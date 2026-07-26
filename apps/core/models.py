"""Core models: AppState singleton and AuditEvent."""

import uuid

from django.conf import settings
from django.db import models

from apps.core.enums import AuditAction


class AppState(models.Model):
    """Singleton runtime state; id is always 1."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    monitoring_paused = models.BooleanField(default=False)
    pause_reason = models.CharField(max_length=255, blank=True, default="")
    worker_heartbeat_at = models.DateTimeField(null=True, blank=True, db_index=True)
    worker_instance_id = models.CharField(max_length=100, blank=True, default="")
    last_cleanup_at = models.DateTimeField(null=True, blank=True)
    safety_block_until = models.DateTimeField(null=True, blank=True)
    safety_block_reason = models.CharField(max_length=255, blank=True, default="")
    safety_ack_required = models.BooleanField(default=False)
    ai_enabled = models.BooleanField(default=True)
    ai_escalation_confidence = models.DecimalField(max_digits=4, decimal_places=3, default="0.750")
    ai_high_value_profit_uah = models.DecimalField(
        max_digits=12, decimal_places=2, default="3000.00"
    )
    market_price_stale_days = models.PositiveSmallIntegerField(default=7)
    old_listing_refresh_hours = models.PositiveSmallIntegerField(default=6)
    scan_run_retention_days = models.PositiveSmallIntegerField(default=90)
    audit_retention_days = models.PositiveSmallIntegerField(default=365)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="appstate_singleton"),
            models.CheckConstraint(
                condition=models.Q(
                    ai_escalation_confidence__gte=0, ai_escalation_confidence__lte=1
                ),
                name="appstate_escalation_confidence_range",
            ),
            models.CheckConstraint(
                condition=models.Q(ai_high_value_profit_uah__gte=0),
                name="appstate_high_value_profit_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(market_price_stale_days__gte=1, market_price_stale_days__lte=30),
                name="appstate_stale_days_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    old_listing_refresh_hours__gte=1, old_listing_refresh_hours__lte=24
                ),
                name="appstate_refresh_hours_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    scan_run_retention_days__gte=7, scan_run_retention_days__lte=365
                ),
                name="appstate_scan_retention_range",
            ),
            models.CheckConstraint(
                condition=models.Q(audit_retention_days__gte=30, audit_retention_days__lte=730),
                name="appstate_audit_retention_range",
            ),
        ]

    def __str__(self) -> str:
        return "AppState"

    def save(self, *args: object, **kwargs: object) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "AppState":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=64, choices=AuditAction.choices)
    target_type = models.CharField(max_length=64, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    changes = models.JSONField(default=dict, blank=True)
    request_id = models.UUIDField(null=True, blank=True, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["action", "-created_at"], name="audit_action_created_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.target_type}:{self.target_id}"
