"""Monitoring enums."""

from django.db import models


class ItemType(models.TextChoices):
    PHONE = "PHONE"
    ACCESSORY = "ACCESSORY"
    PARTS = "PARTS"
    COPY = "COPY"
    UNKNOWN = "UNKNOWN"


class SellerType(models.TextChoices):
    PRIVATE = "PRIVATE"
    BUSINESS = "BUSINESS"
    UNKNOWN = "UNKNOWN"


class DecisionStatus(models.TextChoices):
    NEW = "NEW"
    CANDIDATE = "CANDIDATE"
    REVIEWED = "REVIEWED"
    CONTACTED = "CONTACTED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"
    BOUGHT = "BOUGHT"
    SOLD = "SOLD"
    ARCHIVED = "ARCHIVED"


class AnalysisState(models.TextChoices):
    NOT_RUN = "NOT_RUN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RiskLevel(models.TextChoices):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SnapshotSource(models.TextChoices):
    SEARCH = "SEARCH"
    DETAIL = "DETAIL"
    REFRESH = "REFRESH"


class ScanRunStatus(models.TextChoices):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
