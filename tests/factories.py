"""Plain factory helpers (no factory_boy) with sensible defaults."""

import uuid
from decimal import Decimal

from django.utils import timezone

from apps.monitoring.models import Listing, SearchProfile
from apps.pricing.models import DefectReserveRule, MarketPriceRule

_counter = {"value": 0}


def _next() -> int:
    _counter["value"] += 1
    return _counter["value"]


def create_profile(**overrides) -> SearchProfile:
    index = _next()
    defaults = {
        "name": f"Профиль {index}",
        "olx_url": f"https://www.olx.ua/uk/list/q-iphone-13/?page={index}",
        "canonical_url": f"https://www.olx.ua/uk/list/q-iphone-13/?page={index}",
        "target_models": ["iphone_13"],
        "target_storage_gb": [128],
        "min_price_uah": Decimal("3000.00"),
        "max_purchase_price_uah": Decimal("12500.00"),
        "min_expected_profit_uah": Decimal("1800.00"),
        "min_roi_percent": Decimal("12.00"),
        "next_scan_at": timezone.now(),
    }
    defaults.update(overrides)
    return SearchProfile.objects.create(**defaults)


def create_listing(**overrides) -> Listing:
    index = _next()
    defaults = {
        "olx_id": f"9{index:08d}",
        "canonical_url": f"https://www.olx.ua/d/uk/obyavlenie/iphone-13-{index}-ID9{index:08d}.html",
        "title": "iPhone 13 128GB Midnight",
        "description": "Стан добрий, АКБ 87%. Face ID працює.",
        "current_price_uah": Decimal("11500.00"),
        "model_key": "iphone_13",
        "storage_gb": 128,
        "seller_type": "PRIVATE",
        "last_seen_at": timezone.now(),
    }
    defaults.update(overrides)
    return Listing.objects.create(**defaults)


def create_market_rule(**overrides) -> MarketPriceRule:
    defaults = {
        "model_key": "iphone_13",
        "storage_gb": 128,
        "sim_variant": "ANY",
        "expected_final_sale_price_uah": Decimal("14800.00"),
        "acquisition_shipping_uah": Decimal("150.00"),
        "other_cost_reserve_uah": Decimal("250.00"),
        "checked_at": timezone.now(),
        "is_active": True,
    }
    defaults.update(overrides)
    return MarketPriceRule.objects.create(**defaults)


def create_defect_rule(**overrides) -> DefectReserveRule:
    defaults = {
        "code": "BATTERY_85_89",
        "model_key": "",
        "label": "АКБ 85–89%",
        "amount_uah": Decimal("500.00"),
        "exclusive_group": "BATTERY",
        "priority": 100,
        "is_active": True,
    }
    defaults.update(overrides)
    return DefectReserveRule.objects.create(**defaults)


def unique_olx_id() -> str:
    return uuid.uuid4().hex[:12]
