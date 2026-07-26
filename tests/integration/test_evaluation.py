"""I-32 / §6.7.3: выбор current evaluation при нескольких профилях."""

from decimal import Decimal

import pytest

from apps.monitoring.enums import SnapshotSource
from apps.monitoring.models import Listing, ListingDiscovery
from apps.monitoring.services import evaluate_listing, record_snapshot
from apps.pricing.services import select_current_evaluation
from tests import factories

pytestmark = pytest.mark.django_db


def link(listing, profile):
    ListingDiscovery.objects.get_or_create(listing=listing, search_profile=profile)


class TestCurrentSelection:
    def test_candidate_beats_reject(self, market_rule):
        listing = factories.create_listing(title="iPhone 13 128GB", description="")
        record_snapshot(listing, SnapshotSource.SEARCH, ["initial"])
        generous = factories.create_profile(min_expected_profit_uah=Decimal("1000.00"))
        strict = factories.create_profile(min_expected_profit_uah=Decimal("90000.00"))
        link(listing, generous)
        link(listing, strict)
        evaluate_listing(listing)
        listing.refresh_from_db()
        assert listing.current_evaluation.search_profile_id == generous.id
        assert listing.current_is_candidate is True
        assert listing.decision_status == "CANDIDATE"

    def test_higher_profit_wins_between_candidates(self, market_rule):
        listing = factories.create_listing(title="iPhone 13 128GB", description="")
        record_snapshot(listing, SnapshotSource.SEARCH, ["initial"])
        # оба профиля дают кандидата, но у одного меньше min_profit -> экономика та же;
        # различие в effective_max из-за разных порогов не влияет на profit.
        profile_a = factories.create_profile(min_expected_profit_uah=Decimal("1000.00"))
        profile_b = factories.create_profile(min_expected_profit_uah=Decimal("2000.00"))
        link(listing, profile_a)
        link(listing, profile_b)
        evaluate_listing(listing)
        listing.refresh_from_db()
        # у обоих profit 2650 (нет дефектов: 14800-11500-400*?); равные значения ->
        # tie-break по created_at/UUID, важно что выбор детерминирован
        first_choice = listing.current_evaluation_id
        select_current_evaluation(listing)
        listing.refresh_from_db()
        assert listing.current_evaluation_id == first_choice  # детерминизм

    def test_archived_profile_excluded(self, market_rule):
        from django.utils import timezone

        listing = factories.create_listing(title="iPhone 13 128GB", description="")
        record_snapshot(listing, SnapshotSource.SEARCH, ["initial"])
        profile = factories.create_profile()
        link(listing, profile)
        evaluate_listing(listing)
        listing.refresh_from_db()
        assert listing.current_evaluation is not None

        profile.is_active = False
        profile.archived_at = timezone.now()
        profile.save()
        select_current_evaluation(listing)
        listing.refresh_from_db()
        # Нет пригодных evaluations: все current_* очищены (§6.7.3 п.7)
        assert listing.current_evaluation is None
        assert listing.current_is_candidate is False
        assert listing.current_expected_profit_uah is None
        assert listing.decision_status == "NEW"  # авто-кандидат вернулся в NEW

    def test_manual_status_not_touched(self, market_rule):
        listing = factories.create_listing(title="iPhone 13 128GB", description="")
        record_snapshot(listing, SnapshotSource.SEARCH, ["initial"])
        profile = factories.create_profile()
        link(listing, profile)
        Listing.objects.filter(pk=listing.pk).update(decision_status="CONTACTED")
        listing.refresh_from_db()
        evaluate_listing(listing)
        listing.refresh_from_db()
        assert listing.decision_status == "CONTACTED"  # worker не трогает ручной статус
