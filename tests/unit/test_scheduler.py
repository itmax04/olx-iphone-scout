"""Scheduler: due selection, jitter bounds, backoff ladder."""

import random
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.monitoring.scheduler import (
    apply_failure_backoff,
    compute_interval_seconds,
    schedule_next_scan,
    select_due_profile,
)
from tests import factories

pytestmark = pytest.mark.django_db


class TestDueSelection:
    def test_due_profile_selected(self):
        profile = factories.create_profile(next_scan_at=timezone.now() - timedelta(minutes=1))
        assert select_due_profile() == profile

    def test_future_profile_not_selected(self):
        factories.create_profile(next_scan_at=timezone.now() + timedelta(minutes=5))
        assert select_due_profile() is None

    def test_inactive_and_archived_skipped(self):
        factories.create_profile(
            is_active=False, next_scan_at=timezone.now() - timedelta(minutes=1)
        )
        factories.create_profile(
            archived_at=timezone.now(), next_scan_at=timezone.now() - timedelta(minutes=1)
        )
        assert select_due_profile() is None

    def test_blocked_profile_skipped(self):
        factories.create_profile(
            next_scan_at=timezone.now() - timedelta(minutes=1),
            blocked_until=timezone.now() + timedelta(minutes=10),
        )
        assert select_due_profile() is None

    def test_running_profile_skipped(self):
        factories.create_profile(
            next_scan_at=timezone.now() - timedelta(minutes=1), is_running=True
        )
        assert select_due_profile() is None


class TestInterval:
    def test_jitter_within_bounds_and_min_60(self):
        profile = factories.create_profile(interval_seconds=60, jitter_seconds=15)
        rng = random.Random(42)
        for _ in range(50):
            interval = compute_interval_seconds(profile, rng)
            assert 60 <= interval <= 75  # никогда ниже OLX_MIN_INTERVAL_SECONDS

    def test_schedule_next_scan_success_resets_errors(self):
        profile = factories.create_profile(consecutive_failures=3, last_error_code="OLX_TIMEOUT")
        schedule_next_scan(profile, success=True, rng=random.Random(1))
        profile.refresh_from_db()
        assert profile.consecutive_failures == 0
        assert profile.last_error_code == ""
        assert profile.next_scan_at > timezone.now()


class TestBackoff:
    def test_ladder_5_15_60(self):
        profile = factories.create_profile()
        now = timezone.now()
        expectations = [(1, 5), (2, 15), (3, 60), (4, 60)]
        for expected_failures, minutes in expectations:
            apply_failure_backoff(profile, error_code="OLX_TIMEOUT", message="timeout")
            profile.refresh_from_db()
            assert profile.consecutive_failures == expected_failures
            delta = profile.next_scan_at - now
            assert timedelta(minutes=minutes - 1) < delta < timedelta(minutes=minutes + 2)
