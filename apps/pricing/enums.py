"""Pricing enums."""

from django.db import models


class SimVariant(models.TextChoices):
    ANY = "ANY"
    PHYSICAL = "PHYSICAL"
    ESIM_ONLY = "ESIM_ONLY"
