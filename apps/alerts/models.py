"""Alerts models: transactional notification outbox."""

import uuid

from django.db import models
from django.utils import timezone

from apps.alerts.enums import OutboxEventType, OutboxStatus


class NotificationOutbox(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        "monitoring.Listing",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbox_items",
    )
    event_type = models.CharField(max_length=32, choices=OutboxEventType.choices)
    fingerprint = models.CharField(max_length=64, unique=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16, choices=OutboxStatus.choices, default=OutboxStatus.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    telegram_message_id = models.CharField(max_length=64, blank=True, default="")
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    last_error_message = models.CharField(max_length=500, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attempts__lte=20), name="outbox_attempts_range"
            ),
        ]
        indexes = [
            models.Index(
                fields=["next_attempt_at"],
                name="outbox_due_idx",
                condition=models.Q(status__in=["PENDING", "RETRY"]),
            ),
            models.Index(fields=["status", "-created_at"], name="outbox_status_idx"),
        ]
        ordering = ["-created_at"]
        verbose_name_plural = "notification outbox"

    def __str__(self) -> str:
        return f"{self.event_type} [{self.status}]"
