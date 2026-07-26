"""Deep-tier escalation rules (§6.8). Formal conditions only."""

from decimal import Decimal

from apps.analysis.schemas import AiResultV1
from apps.monitoring.models import Listing

_ESCALATION_DEFECTS = {"WATER_DAMAGE", "UNKNOWN_REPAIR_HISTORY"}


def should_escalate(
    result: AiResultV1 | None,
    listing: Listing,
    *,
    escalation_confidence: Decimal,
    high_value_profit: Decimal,
    fast_schema_failed: bool = False,
) -> tuple[bool, str]:
    """Return (escalate, reason)."""
    if fast_schema_failed:
        return True, "fast_schema_failed"
    if result is None:
        return False, ""

    if Decimal(str(result.confidence)) < escalation_confidence:
        return True, "low_confidence"

    if result.model.value is None or result.storage_gb.value is None:
        return True, "model_or_storage_ambiguous"

    if any(code in _ESCALATION_DEFECTS for code in result.defects):
        return True, "high_risk_signals"
    if result.icloud_status.status == "locked" or result.mdm_status.status == "locked":
        return True, "lock_signals"

    if (
        listing.current_expected_sale_price_uah is not None
        and listing.current_price_uah is not None
        and listing.current_expected_sale_price_uah > 0
    ):
        discount = (
            listing.current_expected_sale_price_uah - listing.current_price_uah
        ) / listing.current_expected_sale_price_uah
        if discount > Decimal("0.40"):
            return True, "deep_discount"

    if (
        listing.current_expected_profit_uah is not None
        and listing.current_expected_profit_uah >= high_value_profit
    ):
        return True, "high_value"

    return False, ""
