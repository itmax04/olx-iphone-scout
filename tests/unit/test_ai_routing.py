"""U-26..U-28: маршрутизация fast/deep и работа при выключенном AI."""

from decimal import Decimal

import pytest

from apps.analysis.routing import should_escalate
from apps.analysis.schemas import validate_ai_result
from tests.unit.test_ai_schema import VALID

pytestmark = pytest.mark.django_db


def make_result(**overrides):
    return validate_ai_result({**VALID, **overrides})


ESCALATION_CONFIDENCE = Decimal("0.750")
HIGH_VALUE = Decimal("3000.00")


def check(result, listing, **kwargs):
    return should_escalate(
        result,
        listing,
        escalation_confidence=ESCALATION_CONFIDENCE,
        high_value_profit=HIGH_VALUE,
        **kwargs,
    )


def test_normal_listing_stays_fast(listing):
    escalate, _ = check(make_result(), listing)
    assert escalate is False  # U-26


def test_low_confidence_escalates(listing):
    escalate, reason = check(make_result(confidence=0.5), listing)
    assert escalate and reason == "low_confidence"  # U-27


def test_unknown_model_escalates(listing):
    result = make_result(model={"value": None, "source": "unknown", "evidence": None})
    escalate, reason = check(result, listing)
    assert escalate and reason == "model_or_storage_ambiguous"


def test_water_damage_escalates(listing):
    escalate, reason = check(make_result(defects=["WATER_DAMAGE"]), listing)
    assert escalate and reason == "high_risk_signals"


def test_mdm_lock_escalates(listing):
    result = make_result(mdm_status={"status": "locked", "source": "stated", "evidence": "MDM"})
    escalate, reason = check(result, listing)
    assert escalate and reason == "lock_signals"


def test_high_value_escalates(listing):
    listing.current_expected_profit_uah = Decimal("3500.00")
    escalate, reason = check(make_result(), listing)
    assert escalate and reason == "high_value"


def test_deep_discount_escalates(listing):
    listing.current_expected_sale_price_uah = Decimal("20000.00")
    listing.current_price_uah = Decimal("10000.00")
    escalate, reason = check(make_result(), listing)
    assert escalate and reason == "deep_discount"


def test_schema_failure_escalates(listing):
    escalate, reason = check(None, listing, fast_schema_failed=True)
    assert escalate and reason == "fast_schema_failed"


def test_ai_disabled_returns_none(listing, settings):
    """U-28: AI выключен — analyze_listing возвращает None без исключений."""
    settings.AI_ENABLED = False
    from apps.analysis.services import analyze_listing

    assert analyze_listing(listing) is None
