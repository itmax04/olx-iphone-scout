"""Monitoring models: SearchProfile, Listing, discovery, snapshots, scan runs."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.monitoring.enums import (
    AnalysisState,
    DecisionStatus,
    ItemType,
    RiskLevel,
    ScanRunStatus,
    SellerType,
    SnapshotSource,
)


class SearchProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    olx_url = models.CharField(max_length=2048)
    canonical_url = models.CharField(max_length=2048, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    target_models = models.JSONField(default=list)
    target_storage_gb = models.JSONField(default=list)
    min_price_uah = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    max_purchase_price_uah = models.DecimalField(max_digits=12, decimal_places=2)
    min_expected_profit_uah = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("1500")
    )
    min_roi_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("12.00"))
    private_only = models.BooleanField(default=True)
    delivery_required = models.BooleanField(default=False)
    interval_seconds = models.IntegerField(default=90)
    jitter_seconds = models.IntegerField(default=15)
    max_cards = models.PositiveSmallIntegerField(default=30)
    included_keywords = models.JSONField(default=list, blank=True)
    excluded_keywords = models.JSONField(default=list, blank=True)
    next_scan_at = models.DateTimeField(default=timezone.now)
    last_scan_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.IntegerField(default=0)
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    last_error_message = models.CharField(max_length=500, blank=True, default="")
    blocked_until = models.DateTimeField(null=True, blank=True)
    is_running = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(min_price_uah__gte=0), name="profile_min_price_gte_0"
            ),
            models.CheckConstraint(
                condition=models.Q(max_purchase_price_uah__gt=0),
                name="profile_max_price_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(max_purchase_price_uah__gt=models.F("min_price_uah")),
                name="profile_max_gt_min",
            ),
            models.CheckConstraint(
                condition=models.Q(min_expected_profit_uah__gte=0),
                name="profile_min_profit_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(min_roi_percent__gte=0, min_roi_percent__lte=100),
                name="profile_roi_range",
            ),
            models.CheckConstraint(
                condition=models.Q(interval_seconds__gte=60, interval_seconds__lte=3600),
                name="profile_interval_range",
            ),
            models.CheckConstraint(
                condition=models.Q(jitter_seconds__gte=0, jitter_seconds__lte=60),
                name="profile_jitter_range",
            ),
            models.CheckConstraint(
                condition=models.Q(max_cards__gte=5, max_cards__lte=50),
                name="profile_max_cards_range",
            ),
            models.CheckConstraint(
                condition=models.Q(consecutive_failures__gte=0),
                name="profile_failures_gte_0",
            ),
        ]
        indexes = [
            models.Index(
                fields=["next_scan_at"],
                name="profile_due_idx",
                condition=models.Q(is_active=True, archived_at__isnull=True),
            ),
            models.Index(fields=["last_success_at"], name="profile_last_success_idx"),
            models.Index(fields=["consecutive_failures"], name="profile_failures_idx"),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Listing(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    olx_id = models.CharField(max_length=64, unique=True)
    canonical_url = models.CharField(max_length=2048)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    current_price_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, default="UAH")
    model_key = models.CharField(max_length=40, blank=True, default="", db_index=True)
    storage_gb = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    item_type = models.CharField(
        max_length=20, choices=ItemType.choices, default=ItemType.UNKNOWN
    )
    location = models.CharField(max_length=255, blank=True, default="")
    seller_name = models.CharField(max_length=120, blank=True, default="")
    seller_profile_url = models.CharField(max_length=2048, blank=True, default="")
    seller_type = models.CharField(
        max_length=16, choices=SellerType.choices, default=SellerType.UNKNOWN
    )
    seller_joined_text = models.CharField(max_length=120, blank=True, default="")
    seller_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    seller_delivery_count = models.IntegerField(null=True, blank=True)
    delivery_available = models.BooleanField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    primary_image_url = models.CharField(max_length=2048, blank=True, default="")
    photo_urls = models.JSONField(default=list, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_detail_fetched_at = models.DateTimeField(null=True, blank=True)
    next_refresh_at = models.DateTimeField(null=True, blank=True, db_index=True)
    title_hash = models.CharField(max_length=64, blank=True, default="")
    content_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    photos_hash = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    inactive_reason = models.CharField(max_length=64, blank=True, default="")
    analysis_status = models.CharField(
        max_length=16, choices=AnalysisState.choices, default=AnalysisState.NOT_RUN
    )
    current_risk_level = models.CharField(
        max_length=16, choices=RiskLevel.choices, default=RiskLevel.UNKNOWN
    )
    current_expected_sale_price_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    current_total_reserve_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    current_expected_total_investment_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    current_expected_profit_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, db_index=True
    )
    current_roi_percent = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    current_effective_max_purchase_price_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    current_is_candidate = models.BooleanField(default=False, db_index=True)
    current_evaluation = models.ForeignKey(
        "analysis.Evaluation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="current_for_listings",
    )
    decision_status = models.CharField(
        max_length=16, choices=DecisionStatus.choices, default=DecisionStatus.NEW
    )
    manual_notes = models.TextField(blank=True, default="")
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(current_price_uah__isnull=True)
                | models.Q(current_price_uah__gte=0),
                name="listing_price_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(seller_rating__isnull=True)
                | models.Q(seller_rating__gte=0, seller_rating__lte=5),
                name="listing_rating_range",
            ),
            models.CheckConstraint(
                condition=models.Q(seller_delivery_count__isnull=True)
                | models.Q(seller_delivery_count__gte=0),
                name="listing_delivery_count_gte_0",
            ),
        ]
        indexes = [
            models.Index(
                fields=["current_is_candidate", "-first_seen_at"], name="listing_candidate_idx"
            ),
            models.Index(fields=["decision_status", "-updated_at"], name="listing_status_idx"),
            models.Index(
                fields=["model_key", "storage_gb", "current_price_uah"],
                name="listing_model_price_idx",
            ),
            models.Index(fields=["is_active", "next_refresh_at"], name="listing_refresh_idx"),
        ]
        ordering = ["-first_seen_at"]

    def __str__(self) -> str:
        return f"{self.olx_id}: {self.title[:40]}"


class ListingDiscovery(models.Model):
    id = models.BigAutoField(primary_key=True)
    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name="discoveries"
    )
    search_profile = models.ForeignKey(
        SearchProfile, on_delete=models.CASCADE, related_name="discoveries"
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "search_profile"], name="discovery_unique"
            ),
        ]
        indexes = [
            models.Index(
                fields=["search_profile", "-last_seen_at"], name="discovery_profile_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.search_profile_id} -> {self.listing_id}"


class ListingSnapshot(models.Model):
    id = models.BigAutoField(primary_key=True)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="snapshots")
    source = models.CharField(max_length=16, choices=SnapshotSource.choices)
    price_uah = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    title = models.CharField(max_length=255)
    title_hash = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64, blank=True, default="")
    photos_hash = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True)
    changed_fields = models.JSONField(default=list)
    change_fingerprint = models.CharField(max_length=64)
    safe_summary = models.JSONField(default=dict)
    observed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "change_fingerprint"], name="snapshot_unique_fingerprint"
            ),
            models.CheckConstraint(
                condition=models.Q(price_uah__isnull=True) | models.Q(price_uah__gte=0),
                name="snapshot_price_gte_0",
            ),
        ]
        indexes = [
            models.Index(fields=["listing", "-observed_at"], name="snapshot_listing_idx"),
        ]
        ordering = ["-observed_at"]

    def __str__(self) -> str:
        return f"snapshot {self.listing_id} @ {self.observed_at:%Y-%m-%d %H:%M}"


class ScanRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    search_profile = models.ForeignKey(
        SearchProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="scan_runs"
    )
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    status = models.CharField(
        max_length=16, choices=ScanRunStatus.choices, default=ScanRunStatus.RUNNING
    )
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.BigIntegerField(null=True, blank=True)
    found_count = models.IntegerField(default=0)
    new_count = models.IntegerField(default=0)
    changed_count = models.IntegerField(default=0)
    candidate_count = models.IntegerField(default=0)
    retry_count = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    parser_version = models.CharField(max_length=32, default="olx-dom-v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_ms__isnull=True) | models.Q(duration_ms__gte=0),
                name="scanrun_duration_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(found_count__gte=0), name="scanrun_found_gte_0"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-started_at"], name="scanrun_status_idx"),
            models.Index(fields=["search_profile", "-started_at"], name="scanrun_profile_idx"),
        ]
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"run {self.id} [{self.status}]"
