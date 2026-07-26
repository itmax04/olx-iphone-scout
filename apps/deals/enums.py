"""Deals enums."""

from django.db import models


class DealStatus(models.TextChoices):
    IN_STOCK = "IN_STOCK"
    SOLD = "SOLD"
    CANCELLED = "CANCELLED"
