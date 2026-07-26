"""Analysis models: AiAnalysis cache and append-only Evaluation."""

import uuid
from decimal import Decimal

from django.db import models

from apps.analysis.enums import AiStatus, AiTier, EvaluationDecision
from apps.monitoring.enums import RiskLevel


class AiAnalysis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        "monitoring.Listing", on_delete=models.CASCADE, related_name="ai_analyses"
    )
    content_hash = models.CharField(max_length=64)
    tier = models.CharField(max_length=8, choices=AiTier.choices)
    attempt = models.PositiveSmallIntegerField(default=1)
    requested_model_id = models.CharField(max_length=100)
    model_id = models.CharField(max_length=100, blank=True, default="")
    prompt_version = models.CharField(max_length=32)
    schema_version = models.PositiveSmallIntegerField(default=1)
    revision = models.PositiveSmallIntegerField(default=0)
    force_reason = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, choices=AiStatus.choices, default=AiStatus.PENDING)
    result = models.JSONField(null=True, blank=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    risk_level = models.CharField(
        max_length=16, choices=RiskLevel.choices, default=RiskLevel.UNKNOWN
    )
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)
    estimated_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "listing",
                    "content_hash",
                    "tier",
                    "schema_version",
                    "prompt_version",
                    "requested_model_id",
                    "revision",
                    "attempt",
                ],
                name="ai_attempt_unique",
            ),
            models.UniqueConstraint(
                fields=[
                    "listing",
                    "content_hash",
                    "tier",
                    "schema_version",
                    "prompt_version",
                    "requested_model_id",
                    "revision",
                ],
                condition=models.Q(status="SUCCESS"),
                name="ai_success_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(attempt__gte=1, attempt__lte=5), name="ai_attempt_range"
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__isnull=True)
                | models.Q(confidence__gte=0, confidence__lte=1),
                name="ai_confidence_range",
            ),
        ]
        indexes = [
            models.Index(fields=["listing", "-created_at"], name="ai_listing_idx"),
            models.Index(fields=["status", "created_at"], name="ai_status_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AI {self.tier} {self.status} for {self.listing_id}"


class Evaluation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        "monitoring.Listing", on_delete=models.CASCADE, related_name="evaluations"
    )
    listing_snapshot = models.ForeignKey(
        "monitoring.ListingSnapshot", null=True, blank=True, on_delete=models.SET_NULL
    )
    search_profile = models.ForeignKey(
        "monitoring.SearchProfile", null=True, blank=True, on_delete=models.SET_NULL
    )
    ai_analysis = models.ForeignKey(AiAnalysis, null=True, blank=True, on_delete=models.SET_NULL)
    market_price_rule = models.ForeignKey(
        "pricing.MarketPriceRule", null=True, blank=True, on_delete=models.SET_NULL
    )
    formula_version = models.CharField(max_length=32, default="profit-v1")
    input_hash = models.CharField(max_length=64)
    purchase_price_uah = models.DecimalField(max_digits=12, decimal_places=2)
    expected_sale_price_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    shipping_reserve_uah = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    defect_reserve_uah = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    other_reserve_uah = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_reserve_uah = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    expected_total_investment_uah = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    expected_profit_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    roi_percent = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    profile_max_purchase_price_uah = models.DecimalField(max_digits=12, decimal_places=2)
    calculated_max_purchase_price_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    effective_max_purchase_price_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    required_min_profit_uah = models.DecimalField(max_digits=12, decimal_places=2)
    required_min_roi_percent = models.DecimalField(max_digits=6, decimal_places=2)
    decision = models.CharField(max_length=16, choices=EvaluationDecision.choices)
    reason_codes = models.JSONField(default=list)
    applied_reserves = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["listing", "input_hash"], name="evaluation_unique"),
            models.CheckConstraint(
                condition=models.Q(purchase_price_uah__gte=0),
                name="evaluation_price_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(total_reserve_uah__gte=0),
                name="evaluation_reserve_gte_0",
            ),
        ]
        indexes = [
            models.Index(fields=["decision", "-created_at"], name="evaluation_decision_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Evaluation {self.decision} for {self.listing_id}"
