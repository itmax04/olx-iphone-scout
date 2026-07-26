"""F-11 / U-22: детерминированный prefilter и hard stops."""

from decimal import Decimal

import pytest

from apps.analysis.enums import EvaluationDecision
from apps.pricing.services import extract_listing_facts, prefilter
from tests import factories

pytestmark = pytest.mark.django_db


def run_prefilter(listing, profile):
    facts = extract_listing_facts(listing.title, listing.description)
    return prefilter(listing, profile, facts)


class TestHardStops:
    @pytest.mark.parametrize(
        "title,code",
        [
            ("Копия iPhone 13 128gb", "ITEM_COPY"),
            ("Муляж iPhone 13", "ITEM_DUMMY"),
            ("Чехол для iPhone 13", "ITEM_ACCESSORY"),
            ("iPhone 13 на запчастини", "ITEM_PARTS"),
            ("iPhone 13 донор", "ITEM_DONOR"),
        ],
    )
    def test_item_type_hard_stop(self, title, code):
        profile = factories.create_profile()
        listing = factories.create_listing(title=title, description="")
        decision, codes = run_prefilter(listing, profile)
        assert decision == EvaluationDecision.REJECT
        assert code in codes

    def test_icloud_lock(self):
        profile = factories.create_profile()
        listing = factories.create_listing(
            title="iPhone 13 128gb",
            description="Телефон заблокирован iCloud, пароль неизвестен",
        )
        decision, codes = run_prefilter(listing, profile)
        assert decision == EvaluationDecision.REJECT
        assert "ICLOUD_LOCK" in codes

    def test_price_missing(self):
        profile = factories.create_profile()
        listing = factories.create_listing(current_price_uah=None)
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["PRICE_MISSING"])

    def test_currency_unsupported(self):
        profile = factories.create_profile()
        listing = factories.create_listing(currency="USD")
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["CURRENCY_UNSUPPORTED"])

    def test_model_outside_profile(self):
        profile = factories.create_profile(target_models=["iphone_14"])
        listing = factories.create_listing()  # iPhone 13
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["MODEL_UNSUPPORTED"])

    def test_unknown_model(self):
        profile = factories.create_profile()
        listing = factories.create_listing(title="Nokia 3310", description="")
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["MODEL_UNSUPPORTED"])


class TestManualReview:
    def test_ambiguous_model(self):
        profile = factories.create_profile(target_models=["iphone_13", "iphone_14"])
        listing = factories.create_listing(title="Обмен iPhone 13 на iPhone 14", description="")
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.MANUAL_REVIEW, ["MODEL_AMBIGUOUS"])

    def test_storage_unknown(self):
        profile = factories.create_profile()
        listing = factories.create_listing(title="iPhone 13 у гарному стані", description="")
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.MANUAL_REVIEW, ["STORAGE_UNKNOWN"])

    def test_invalid_storage_for_model(self):
        profile = factories.create_profile(
            target_models=["iphone_15_pro_max"], target_storage_gb=[128]
        )
        listing = factories.create_listing(title="iPhone 15 Pro Max 128GB", description="")
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.MANUAL_REVIEW, ["STORAGE_UNKNOWN"])


class TestProfileFilters:
    def test_excluded_keyword(self):
        profile = factories.create_profile(excluded_keywords=["муляж", "икра"])
        listing = factories.create_listing(description="в подарок икра")
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["KEYWORD_EXCLUDED"])

    def test_included_keyword_missing(self):
        profile = factories.create_profile(included_keywords=["гарантия"])
        listing = factories.create_listing()
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["KEYWORD_MISSING"])

    def test_business_seller_rejected_when_private_only(self):
        profile = factories.create_profile(private_only=True)
        listing = factories.create_listing(seller_type="BUSINESS")
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["SELLER_TYPE_MISMATCH"])

    def test_price_below_minimum(self):
        profile = factories.create_profile(min_price_uah=Decimal("5000.00"))
        listing = factories.create_listing(current_price_uah=Decimal("1000.00"))
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["PRICE_BELOW_MINIMUM"])

    def test_storage_mismatch(self):
        profile = factories.create_profile(target_storage_gb=[256])
        listing = factories.create_listing()  # 128
        decision, codes = run_prefilter(listing, profile)
        assert (decision, codes) == (EvaluationDecision.REJECT, ["STORAGE_MISMATCH"])

    def test_clean_listing_continues(self):
        profile = factories.create_profile()
        listing = factories.create_listing(title="iPhone 13 128GB", description="стан супер")
        decision, codes = run_prefilter(listing, profile)
        assert decision == "CONTINUE"
        assert codes == []
