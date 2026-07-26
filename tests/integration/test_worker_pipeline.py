"""Worker pipeline: dedup, snapshots, refresh, recovery, worker loop."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.alerts.models import NotificationOutbox
from apps.core.models import AppState
from apps.monitoring.collectors.fixture_source import FixtureOlxSource
from apps.monitoring.enums import ScanRunStatus
from apps.monitoring.models import Listing, ListingSnapshot, ScanRun
from apps.monitoring.services import (
    process_profile_scan,
    recover_stuck_state,
    refresh_listing,
    select_listings_for_refresh,
)
from tests import factories

pytestmark = pytest.mark.django_db


class TestSnapshots:
    def test_price_change_one_snapshot(self, profile, market_rule):
        process_profile_scan(profile, FixtureOlxSource())
        listing = Listing.objects.get(olx_id="800000001")
        snapshots_before = listing.snapshots.count()

        process_profile_scan(
            profile,
            FixtureOlxSource(
                search_fixture="search_price_drop", detail_fixture="detail_price_drop"
            ),
        )
        listing.refresh_from_db()
        assert listing.current_price_uah == Decimal("10400.00")
        price_snapshots = listing.snapshots.filter(changed_fields__contains="price")
        assert price_snapshots.count() == 1  # F-08: ровно один price-drop snapshot
        assert listing.snapshots.count() > snapshots_before

    def test_unchanged_rescan_no_snapshot(self, profile, market_rule):
        process_profile_scan(profile, FixtureOlxSource())
        count_before = ListingSnapshot.objects.count()
        process_profile_scan(profile, FixtureOlxSource())
        assert ListingSnapshot.objects.count() == count_before  # U-11


class TestRefresh:
    def _prepare_listing(self, profile, market_rule):
        factories.create_defect_rule()  # резерв под АКБ 85–89% из фикстуры
        process_profile_scan(profile, FixtureOlxSource())
        listing = Listing.objects.get(olx_id="800000001")
        Listing.objects.filter(pk=listing.pk).update(
            next_refresh_at=timezone.now() - timedelta(minutes=5)
        )
        listing.refresh_from_db()
        return listing

    def test_refresh_selection(self, profile, market_rule):
        listing = self._prepare_listing(profile, market_rule)
        selected = select_listings_for_refresh()
        assert listing in selected

    def test_refresh_price_drop_creates_alert(self, profile, market_rule):
        """I-26: снижение цены на refresh -> новая Evaluation и один alert."""
        listing = self._prepare_listing(profile, market_rule)
        # Обнуляем кандидат-статус, будто раньше было дорого
        Listing.objects.filter(pk=listing.pk).update(
            current_is_candidate=False, decision_status="NEW"
        )
        listing.refresh_from_db()
        outcome = refresh_listing(listing, FixtureOlxSource(detail_fixture="detail_price_drop"))
        listing.refresh_from_db()
        assert outcome == "price_drop_candidate"
        assert listing.current_price_uah == Decimal("10400.00")
        assert NotificationOutbox.objects.filter(event_type="PRICE_DROP").count() == 1

    def test_refresh_unchanged(self, profile, market_rule):
        listing = self._prepare_listing(profile, market_rule)
        outcome = refresh_listing(listing, FixtureOlxSource())
        assert outcome == "unchanged"  # I-27
        assert NotificationOutbox.objects.filter(event_type="PRICE_DROP").count() == 0

    def test_refresh_inactive_marks_listing(self, profile, market_rule):
        listing = self._prepare_listing(profile, market_rule)
        outcome = refresh_listing(listing, FixtureOlxSource(detail_fixture="detail_inactive"))
        listing.refresh_from_db()
        assert outcome == "inactive"
        assert listing.is_active is False
        assert listing.next_refresh_at is None


class TestRecovery:
    def test_stuck_running_runs_closed(self, profile):
        ScanRun.objects.create(search_profile=profile, status=ScanRunStatus.RUNNING)
        profile.is_running = True
        profile.save(update_fields=["is_running"])
        recovered = recover_stuck_state()
        assert recovered == 1
        profile.refresh_from_db()
        assert profile.is_running is False
        assert ScanRun.objects.filter(status=ScanRunStatus.RUNNING).count() == 0


class TestWorkerLoop:
    def test_worker_cycle_with_fixture_source(self, profile, market_rule, settings):
        settings.MONITOR_ENABLED = True
        from apps.monitoring.worker import MonitorWorker

        worker = MonitorWorker(source=FixtureOlxSource(), max_cycles=3)
        worker.run()
        state = AppState.get_solo()
        assert state.worker_heartbeat_at is not None  # heartbeat записан
        assert Listing.objects.count() == 4  # скан выполнен
        assert ScanRun.objects.filter(status="SUCCESS").exists()

    def test_worker_respects_monitor_disabled(self, profile, settings):
        settings.MONITOR_ENABLED = False
        from apps.monitoring.worker import MonitorWorker

        worker = MonitorWorker(source=FixtureOlxSource(), max_cycles=2)
        worker.run()
        assert Listing.objects.count() == 0  # I-34: env-флаг доминирует
