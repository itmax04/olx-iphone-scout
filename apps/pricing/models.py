"""Pricing models: market price rules and defect reserve rules."""

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.pricing.enums import SimVariant


class MarketPriceRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_key = models.CharField(max_length=40)
    storage_gb = models.PositiveSmallIntegerField()
    sim_variant = models.CharField(
        max_length=16, choices=SimVariant.choices, default=SimVariant.ANY
    )
    expected_final_sale_price_uah = models.DecimalField(max_digits=12, decimal_places=2)
    acquisition_shipping_uah = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    other_cost_reserve_uah = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    checked_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["model_key", "storage_gb", "sim_variant"],
                name="market_rule_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(expected_final_sale_price_uah__gt=0),
                name="market_rule_sale_price_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(acquisition_shipping_uah__gte=0),
                name="market_rule_shipping_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(other_cost_reserve_uah__gte=0),
                name="market_rule_other_gte_0",
            ),
        ]
        indexes = [
            models.Index(
                fields=["is_active", "model_key", "storage_gb"], name="market_rule_lookup_idx"
            ),
        ]
        ordering = ["model_key", "storage_gb", "sim_variant"]

    def __str__(self) -> str:
        return f"{self.model_key} {self.storage_gb}GB {self.sim_variant}"


class DefectReserveRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64)
    model_key = models.CharField(max_length=40, blank=True, default="")
    label = models.CharField(max_length=120)
    amount_uah = models.DecimalField(max_digits=12, decimal_places=2)
    exclusive_group = models.CharField(max_length=64, blank=True, default="")
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code", "model_key"], name="defect_rule_unique"),
            models.CheckConstraint(
                condition=models.Q(amount_uah__gte=0), name="defect_rule_amount_gte_0"
            ),
            models.CheckConstraint(
                condition=models.Q(priority__lte=1000), name="defect_rule_priority_range"
            ),
        ]
        indexes = [
            models.Index(fields=["is_active", "code", "model_key"], name="defect_rule_lookup_idx"),
        ]
        ordering = ["code", "model_key"]

    def __str__(self) -> str:
        scope = self.model_key or "universal"
        return f"{self.code} ({scope}): {self.amount_uah} UAH"
