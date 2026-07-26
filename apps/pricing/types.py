"""Typed immutable DTOs for the deterministic pipeline."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    model_key: str | None
    model_ambiguous: bool
    storage_gb: int | None
    storage_valid: bool
    item_type: str
    defect_codes: tuple[str, ...]
    battery_percent: int | None
    hard_stop_codes: tuple[str, ...]
    manual_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AppliedReserve:
    code: str
    label: str
    amount_uah: Decimal
    rule_id: str
    model_specific: bool


@dataclass(frozen=True, slots=True)
class CalculationResult:
    expected_sale_price_uah: Decimal | None
    shipping_reserve_uah: Decimal
    defect_reserve_uah: Decimal
    other_reserve_uah: Decimal
    total_reserve_uah: Decimal
    expected_total_investment_uah: Decimal
    expected_profit_uah: Decimal | None
    roi_percent: Decimal | None
    calculated_max_purchase_price_uah: Decimal | None
    effective_max_purchase_price_uah: Decimal | None
    applied_reserves: tuple[AppliedReserve, ...] = field(default_factory=tuple)
