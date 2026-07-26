"""U-15..U-25: формула profit-v1, резервы, пороги, точный Decimal."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analysis.enums import EvaluationDecision
from apps.pricing.services import (
    calculate,
    evaluate_listing_for_profile,
    select_defect_reserves,
    select_market_rule,
)
from tests import factories

pytestmark = pytest.mark.django_db


class TestFormula:
    def test_spec_example_numbers(self, market_rule):
        """Пример из ТЗ §11.17: 11500 закупка, 14800 продажа, 900 резерв."""
        factories.create_defect_rule(code="BATTERY_85_89", amount_uah=Decimal("500.00"))
        applied, missing = select_defect_reserves("iphone_13", ("BATTERY_85_89",))
        assert missing == []
        calc = calculate(
            Decimal("11500.00"),
            market_rule,
            applied,
            Decimal("1800.00"),
            Decimal("12500.00"),
        )
        assert calc.total_reserve_uah == Decimal("900.00")  # U-15: 150+250+500
        assert calc.expected_profit_uah == Decimal("2400.00")  # U-16
        assert calc.expected_total_investment_uah == Decimal("12400.00")
        assert calc.roi_percent == Decimal("19.35")  # U-17
        assert calc.calculated_max_purchase_price_uah == Decimal("12100.00")  # U-18
        assert calc.effective_max_purchase_price_uah == Decimal("12100.00")

    def test_roi_null_when_investment_zero(self):
        calc = calculate(Decimal("0"), None, [], Decimal("0"), Decimal("1000"))
        assert calc.roi_percent is None  # не infinity

    def test_negative_profit_allowed(self, market_rule):
        calc = calculate(
            Decimal("14900.00"), market_rule, [], Decimal("1800.00"), Decimal("20000.00")
        )
        assert calc.expected_profit_uah == Decimal("-500.00")


class TestReserveSelection:
    def test_model_specific_overrides_universal(self):
        factories.create_defect_rule(
            code="FRONT_GLASS_CRACK", model_key="", amount_uah=Decimal("1000"), exclusive_group=""
        )
        specific = factories.create_defect_rule(
            code="FRONT_GLASS_CRACK",
            model_key="iphone_13",
            amount_uah=Decimal("1500"),
            exclusive_group="",
        )
        applied, missing = select_defect_reserves("iphone_13", ("FRONT_GLASS_CRACK",))
        assert missing == []
        assert len(applied) == 1
        assert applied[0].rule_id == str(specific.id)
        assert applied[0].amount_uah == Decimal("1500.00")

    def test_exclusive_battery_group_applies_once(self):
        factories.create_defect_rule(code="BATTERY_85_89", amount_uah=Decimal("500"), priority=100)
        factories.create_defect_rule(code="BATTERY_80_84", amount_uah=Decimal("900"), priority=200)
        # Оба кода «обнаружены» (гипотетически): применяется один с высшим приоритетом.
        applied, _ = select_defect_reserves("iphone_13", ("BATTERY_85_89", "BATTERY_80_84"))
        assert len(applied) == 1
        assert applied[0].code == "BATTERY_80_84"

    def test_missing_rule_reported(self):
        applied, missing = select_defect_reserves("iphone_13", ("WATER_DAMAGE",))
        assert applied == []
        assert missing == ["WATER_DAMAGE"]

    def test_inactive_rule_ignored(self):
        factories.create_defect_rule(
            code="CAMERA_DEFECT", amount_uah=Decimal("700"), is_active=False, exclusive_group=""
        )
        applied, missing = select_defect_reserves("iphone_13", ("CAMERA_DEFECT",))
        assert applied == []
        assert missing == ["CAMERA_DEFECT"]


class TestMarketRuleSelection:
    def test_stale_rule_detected(self):
        rule = factories.create_market_rule(checked_at=timezone.now() - timezone.timedelta(days=10))
        found, is_stale = select_market_rule("iphone_13", 128)
        assert found == rule
        assert is_stale is True  # U-20 (default stale = 7 дней)

    def test_missing_rule(self):
        found, is_stale = select_market_rule("iphone_11", 64)
        assert found is None


class TestEvaluationDecisions:
    def test_candidate(self, market_rule):
        profile = factories.create_profile()
        listing = factories.create_listing(title="iPhone 13 128GB", description="стан чудовий")
        evaluation = evaluate_listing_for_profile(listing, profile)
        assert evaluation.decision == EvaluationDecision.CANDIDATE  # U-23
        assert set(evaluation.reason_codes) == {"PROFIT_THRESHOLD_MET", "ROI_THRESHOLD_MET"}

    def test_missing_market_rule_manual(self):
        profile = factories.create_profile()
        listing = factories.create_listing(title="iPhone 13 128GB", description="")
        evaluation = evaluate_listing_for_profile(listing, profile)
        assert evaluation.decision == EvaluationDecision.MANUAL_REVIEW  # U-19
        assert "MARKET_PRICE_MISSING" in evaluation.reason_codes
        assert evaluation.expected_profit_uah is None  # цена не выдумана

    def test_stale_market_rule_manual(self):
        factories.create_market_rule(checked_at=timezone.now() - timezone.timedelta(days=30))
        profile = factories.create_profile()
        listing = factories.create_listing(title="iPhone 13 128GB", description="")
        evaluation = evaluate_listing_for_profile(listing, profile)
        assert evaluation.decision == EvaluationDecision.MANUAL_REVIEW
        assert "MARKET_PRICE_STALE" in evaluation.reason_codes  # U-20

    def test_low_profit_reject(self, market_rule):
        profile = factories.create_profile(max_purchase_price_uah=Decimal("15000.00"))
        listing = factories.create_listing(
            title="iPhone 13 128GB", description="", current_price_uah=Decimal("13500.00")
        )
        evaluation = evaluate_listing_for_profile(listing, profile)
        assert evaluation.decision == EvaluationDecision.REJECT  # U-25
        assert "PROFIT_BELOW_THRESHOLD" in evaluation.reason_codes

    def test_borderline_manual(self, market_rule):
        # profit = 14800 - price - 400; порог 1800, борд. зона от 1620.
        # price=12700: profit 1700 — выше calculated_max (12600), но ниже
        # профильного потолка 13000 и в пределах 10% от порога -> MANUAL_REVIEW.
        profile = factories.create_profile(max_purchase_price_uah=Decimal("13000.00"))
        listing = factories.create_listing(
            title="iPhone 13 128GB", description="", current_price_uah=Decimal("12700.00")
        )
        evaluation = evaluate_listing_for_profile(listing, profile)
        assert evaluation.decision == EvaluationDecision.MANUAL_REVIEW  # U-24
        assert "PRICE_BORDERLINE" in evaluation.reason_codes

    def test_far_below_threshold_still_reject(self, market_rule):
        # profit 700 (<90% порога) -> обычный REJECT, не borderline.
        profile = factories.create_profile(max_purchase_price_uah=Decimal("14000.00"))
        listing = factories.create_listing(
            title="iPhone 13 128GB", description="", current_price_uah=Decimal("13700.00")
        )
        evaluation = evaluate_listing_for_profile(listing, profile)
        assert evaluation.decision == EvaluationDecision.REJECT

    def test_reserve_rule_missing_manual(self, market_rule):
        profile = factories.create_profile()
        listing = factories.create_listing(
            title="iPhone 13 128GB",
            description="Трещина на экране, торг",
        )
        evaluation = evaluate_listing_for_profile(listing, profile)
        assert evaluation.decision == EvaluationDecision.MANUAL_REVIEW
        assert "RESERVE_RULE_MISSING" in evaluation.reason_codes  # F-13

    def test_hard_stop_beats_profit(self, market_rule):
        """U-22: activation lock отклоняется независимо от прибыли."""
        profile = factories.create_profile()
        listing = factories.create_listing(
            title="iPhone 13 128GB",
            description="icloud заблокирован, цена низкая",
            current_price_uah=Decimal("2000.00"),
        )
        evaluation = evaluate_listing_for_profile(listing, profile)
        assert evaluation.decision == EvaluationDecision.REJECT
        assert "ICLOUD_LOCK" in evaluation.reason_codes

    def test_same_input_same_hash(self, market_rule):
        """I-25 аналог: одинаковый вход дает ту же Evaluation (idempotent)."""
        profile = factories.create_profile()
        listing = factories.create_listing(title="iPhone 13 128GB", description="")
        first = evaluate_listing_for_profile(listing, profile)
        second = evaluate_listing_for_profile(listing, profile)
        assert first.id == second.id
        assert first.input_hash == second.input_hash
