"""Analysis enums."""

from django.db import models


class AiTier(models.TextChoices):
    FAST = "FAST"
    DEEP = "DEEP"


class AiStatus(models.TextChoices):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class EvaluationDecision(models.TextChoices):
    CANDIDATE = "CANDIDATE"
    REJECT = "REJECT"
    MANUAL_REVIEW = "MANUAL_REVIEW"
