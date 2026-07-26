"""Deals models: one Deal per Listing with an immutable purchase snapshot."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.deals.enums import DealStatus


class Deal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.OneToOneField(
        "monitoring.Listing", on_delete=models.PROTECT, related_name="deal"
    )
    source_evaluation = models.ForeignKey(
        "analysis.Evaluation", null=True, blank=True, on_delete=models.SET_NULL
    )
    listing_status_before_purchase = models.CharField(max_length=16)
    purchase_snapshot = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16, choices=DealStatus.choices, default=DealStatus.IN_STOCK
    )
    purchase_price_uah = models.DecimalField(max_digits=12, decimal_places=2)
    purchased_at = models.DateTimeField()
    acquisition_shipping_uah = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    repair_cost_uah = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    other_cost_uah = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    sale_price_uah = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sold_at = models.DateTimeField(null=True, blank=True)
    realized_profit_uah = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purchase_price_uah__gt=0), name="deal_price_gt_0"
            ),
            models.CheckConstraint(
                condition=models.Q(acquisition_shipping_uah__gte=0),
                name="deal_shipping_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(repair_cost_uah__gte=0), name="deal_repair_gte_0"
            ),
            models.CheckConstraint(
                condition=models.Q(other_cost_uah__gte=0), name="deal_other_gte_0"
            ),
            models.CheckConstraint(
                condition=models.Q(sale_price_uah__isnull=True) | models.Q(sale_price_uah__gt=0),
                name="deal_sale_price_gt_0",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-purchased_at"], name="deal_status_idx"),
            models.Index(fields=["sold_at"], name="deal_sold_idx"),
        ]
        ordering = ["-purchased_at"]

    def __str__(self) -> str:
        return f"Deal {self.status} for {self.listing_id}"
