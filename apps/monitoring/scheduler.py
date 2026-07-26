"""Due-profile selection, next-scan scheduling and failure backoff."""

import random
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.monitoring.models import SearchProfile

# Backoff ladder for ordinary errors (§6.5): 5, 15, then 60 minutes.
BACKOFF_MINUTES = (5, 15, 60)


def select_due_profile() -> SearchProfile | None:
    now = timezone.now()
    return (
        SearchProfile.objects.filter(
            is_active=True,
            archived_at__isnull=True,
            is_running=False,
            next_scan_at__lte=now,
        )
        .exclude(blocked_until__gt=now)
        .order_by("next_scan_at")
        .first()
    )


def compute_interval_seconds(profile: SearchProfile, rng: random.Random | None = None) -> int:
    rng = rng or random.Random()
    jitter = rng.randint(-profile.jitter_seconds, profile.jitter_seconds)
    interval = profile.interval_seconds + jitter
    return max(interval, settings.OLX_MIN_INTERVAL_SECONDS)


def schedule_next_scan(
    profile: SearchProfile, *, success: bool, rng: random.Random | None = None
) -> None:
    now = timezone.now()
    interval = compute_interval_seconds(profile, rng)
    update = {
        "last_scan_at": now,
        "next_scan_at": now + timedelta(seconds=interval),
    }
    if success:
        update.update(
            {
                "last_success_at": now,
                "consecutive_failures": 0,
                "last_error_code": "",
                "last_error_message": "",
                "blocked_until": None,
            }
        )
    SearchProfile.objects.filter(pk=profile.pk).update(**update)


def apply_failure_backoff(profile: SearchProfile, *, error_code: str, message: str) -> None:
    now = timezone.now()
    failures = profile.consecutive_failures + 1
    ladder_index = min(failures, len(BACKOFF_MINUTES)) - 1
    cooldown = timedelta(minutes=BACKOFF_MINUTES[ladder_index])
    SearchProfile.objects.filter(pk=profile.pk).update(
        last_scan_at=now,
        next_scan_at=now + cooldown,
        blocked_until=now + cooldown,
        consecutive_failures=failures,
        last_error_code=error_code[:64],
        last_error_message=message[:500],
    )
