"""Alerts enums."""

from django.db import models


class OutboxEventType(models.TextChoices):
    NEW_CANDIDATE = "NEW_CANDIDATE"
    PRICE_DROP = "PRICE_DROP"
    CONTENT_CHANGED = "CONTENT_CHANGED"
    CAPTCHA = "CAPTCHA"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    RECOVERED = "RECOVERED"
    TEST = "TEST"


class OutboxStatus(models.TextChoices):
    PENDING = "PENDING"
    SENDING = "SENDING"
    RETRY = "RETRY"
    SENT = "SENT"
    FAILED = "FAILED"
