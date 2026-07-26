"""I-05..I-11: полный проход скана через fixture source."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import AppState
from apps.monitoring.collectors.fixture_source import FixtureOlxSource
from apps.monitoring.models import Listing, ListingDiscovery, ScanRun
from apps.monitoring.services import process_profile_scan
from tests import factories

pytestmark = pytest.mark.django_db


def test_scan_creates_listings_and_discoveries(profile, market_rule):
    run = process_profile_scan(profile, FixtureOlxSource())
    assert run.status == "SUCCESS"
    assert run.found_count == 4
    assert Listing.objects.count() == 4  # I-05
    assert ListingDiscovery.objects.filter(search_profile=profile).count() == 4


def test_repeat_scan_no_duplicates(profile, market_rule):
    process_profile_scan(profile, FixtureOlxSource())
    process_profile_scan(profile, FixtureOlxSource())
    assert Listing.objects.count() == 4  # I-06
    assert ListingDiscovery.objects.count() == 4


def test_detail_fields_populated(profile, market_rule):
    process_profile_scan(profile, FixtureOlxSource())
    listing = Listing.objects.get(olx_id="800000001")
    assert listing.current_price_uah == Decimal("11500.00")
    assert listing.model_key == "iphone_13"
    assert "АКБ 87%" in (listing.description or "")  # I-07
    assert len(listing.photo_urls) == 2
    assert listing.delivery_available is True
    assert listing.next_refresh_at is not None


def test_captcha_blocks_and_pauses(profile):
    run = process_profile_scan(profile, FixtureOlxSource(search_fixture="captcha"))
    assert run.status == "BLOCKED"  # I-10
    assert run.error_code == "OLX_CAPTCHA"
    state = AppState.get_solo()
    assert state.monitoring_paused is True
    assert state.safety_ack_required is True
    assert state.safety_block_until is not None
    profile.refresh_from_db()
    assert profile.consecutive_failures == 1
    assert profile.blocked_until is not None  # I-11: без tight loop


def test_layout_change_is_explicit_failure(profile):
    class BrokenSource(FixtureOlxSource):
        def fetch_search(self, url, *, max_cards):
            from apps.monitoring.collectors.olx_parser import parse_search_page

            return parse_search_page("<html><body>новая верстка</body></html>")

    run = process_profile_scan(profile, BrokenSource())
    assert run.status == "FAILED"  # I-09: не ложный пустой успех
    assert run.error_code == "OLX_LAYOUT_CHANGED"
    assert ScanRun.objects.filter(status="FAILED").count() == 1


def test_two_profiles_one_listing(market_rule):
    profile_a = factories.create_profile()
    profile_b = factories.create_profile()
    process_profile_scan(profile_a, FixtureOlxSource())
    process_profile_scan(profile_b, FixtureOlxSource())
    assert Listing.objects.count() == 4  # F-07: дедупликация между профилями
    listing = Listing.objects.get(olx_id="800000001")
    assert listing.discoveries.count() == 2


def test_schedule_updated_after_success(profile, market_rule):
    before = timezone.now()
    process_profile_scan(profile, FixtureOlxSource())
    profile.refresh_from_db()
    assert profile.last_success_at is not None
    assert profile.next_scan_at > before
