"""I-28, F-23/F-24: сделки, snapshot, отмена, фактическая прибыль Decimal."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.exceptions import ApiError, ConflictError
from apps.deals.models import Deal
from apps.deals.services import create_deal, update_deal
from tests import factories

pytestmark = pytest.mark.django_db


def buy(listing, **overrides):
    data = {
        "purchase_price_uah": Decimal("11500.00"),
        "purchased_at": timezone.now(),
        "acquisition_shipping_uah": Decimal("100.00"),
        "repair_cost_uah": Decimal("500.00"),
        "other_cost_uah": Decimal("100.00"),
        "notes": "Замена защитного стекла",
    }
    data.update(overrides)
    return create_deal(listing, data)


class TestCreate:
    def test_snapshot_copied_and_status_bought(self):
        listing = factories.create_listing(decision_status="CONTACTED")
        deal = buy(listing)
        listing.refresh_from_db()
        assert listing.decision_status == "BOUGHT"
        assert deal.listing_status_before_purchase == "CONTACTED"
        assert deal.purchase_snapshot["olx_id"] == listing.olx_id  # I-28
        assert deal.purchase_snapshot["title"] == listing.title
        assert deal.status == "IN_STOCK"
        assert deal.realized_profit_uah is None

    def test_second_deal_forbidden(self):
        listing = factories.create_listing()
        buy(listing)
        with pytest.raises(ConflictError):
            buy(listing)

    def test_zero_price_rejected(self):
        listing = factories.create_listing()
        with pytest.raises(ApiError):
            buy(listing, purchase_price_uah=Decimal("0"))


class TestSold:
    def test_realized_profit_decimal(self):
        listing = factories.create_listing()
        deal = buy(listing)
        deal = update_deal(
            deal,
            {
                "status": "SOLD",
                "sale_price_uah": Decimal("14500.00"),
                "sold_at": timezone.now(),
            },
        )
        # 14500 - (11500 + 100 + 500 + 100) = 2300.00 (пример из ТЗ §11.17)
        assert deal.realized_profit_uah == Decimal("2300.00")
        assert isinstance(deal.realized_profit_uah, Decimal)
        deal.listing.refresh_from_db()
        assert deal.listing.decision_status == "SOLD"

    def test_sold_requires_sale_fields(self):
        listing = factories.create_listing()
        deal = buy(listing)
        with pytest.raises(ApiError):
            update_deal(deal, {"status": "SOLD"})

    def test_sold_date_before_purchase_rejected(self):
        listing = factories.create_listing()
        deal = buy(listing)
        with pytest.raises(ApiError):
            update_deal(
                deal,
                {
                    "status": "SOLD",
                    "sale_price_uah": Decimal("14000.00"),
                    "sold_at": deal.purchased_at - timezone.timedelta(days=1),
                },
            )

    def test_sold_cannot_revert(self):
        listing = factories.create_listing()
        deal = buy(listing)
        update_deal(
            deal,
            {"status": "SOLD", "sale_price_uah": Decimal("14000.00"), "sold_at": timezone.now()},
        )
        with pytest.raises(ConflictError):
            update_deal(deal, {"status": "IN_STOCK"})


class TestCancellation:
    def test_cancel_restores_listing_status(self):
        listing = factories.create_listing(decision_status="CONTACTED")
        deal = buy(listing)
        deal = update_deal(deal, {"status": "CANCELLED"})
        listing.refresh_from_db()
        assert listing.decision_status == "CONTACTED"  # restore
        assert deal.status == "CANCELLED"
        assert Deal.objects.count() == 1

    def test_rebuy_reuses_same_deal(self):
        listing = factories.create_listing(decision_status="CONTACTED")
        deal = buy(listing)
        update_deal(deal, {"status": "CANCELLED"})
        second = buy(listing, purchase_price_uah=Decimal("11000.00"))
        assert second.id == deal.id  # тот же Deal, не второй
        assert second.status == "IN_STOCK"
        assert second.purchase_price_uah == Decimal("11000.00")
        assert Deal.objects.count() == 1


class TestOptimisticLocking:
    def test_stale_updated_at_conflict(self):
        listing = factories.create_listing()
        deal = buy(listing)
        with pytest.raises(ConflictError):
            update_deal(
                deal,
                {"repair_cost_uah": Decimal("600.00")},
                expected_updated_at="2000-01-01T00:00:00",
            )
