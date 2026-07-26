"""Dashboard aggregates. Real numbers only; empty DB gives honest zeros."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.alerts.models import NotificationOutbox
from apps.deals.enums import DealStatus
from apps.deals.models import Deal
from apps.monitoring.enums import DecisionStatus, ScanRunStatus
from apps.monitoring.models import Listing, ScanRun, SearchProfile


def dashboard_stats(period: str = "today") -> dict:
    now = timezone.now()
    if period == "7d":
        since = now - timedelta(days=7)
    elif period == "30d":
        since = now - timedelta(days=30)
    elif period == "month":
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    candidates = Listing.objects.filter(current_is_candidate=True, is_active=True)
    in_stock = Deal.objects.filter(status=DealStatus.IN_STOCK)

    capital = in_stock.aggregate(
        total=Sum("purchase_price_uah")
        + Sum("acquisition_shipping_uah")
        + Sum("repair_cost_uah")
        + Sum("other_cost_uah")
    )["total"] or Decimal("0")

    realized = Deal.objects.filter(status=DealStatus.SOLD, sold_at__gte=month_start).aggregate(
        total=Sum("realized_profit_uah")
    )["total"] or Decimal("0")

    return {
        "new_listings": Listing.objects.filter(first_seen_at__gte=since).count(),
        "candidates": candidates.count(),
        "price_drops": NotificationOutbox.objects.filter(
            event_type="PRICE_DROP", created_at__gte=week_ago
        ).count(),
        "candidate_expected_profit_uah": str(
            candidates.aggregate(total=Sum("current_expected_profit_uah"))["total"] or Decimal("0")
        ),
        "capital_in_stock_uah": str(capital),
        "realized_profit_uah": str(realized),
        "checked_today": ScanRun.objects.filter(started_at__gte=since).count(),
        "errors_today": ScanRun.objects.filter(
            started_at__gte=since, status__in=[ScanRunStatus.FAILED, ScanRunStatus.BLOCKED]
        ).count(),
    }


def recent_candidates(limit: int = 10):
    return Listing.objects.filter(current_is_candidate=True).order_by("-first_seen_at")[:limit]


def recent_errors(limit: int = 5):
    return (
        ScanRun.objects.filter(status__in=[ScanRunStatus.FAILED, ScanRunStatus.BLOCKED])
        .select_related("search_profile")
        .order_by("-started_at")[:limit]
    )


def overdue_profiles(limit: int = 5):
    now = timezone.now()
    return SearchProfile.objects.filter(
        is_active=True,
        archived_at__isnull=True,
        next_scan_at__lt=now - timedelta(minutes=10),
    ).order_by("next_scan_at")[:limit]


def funnel() -> dict:
    counts = {
        "found": Listing.objects.count(),
        "candidates": Listing.objects.filter(
            decision_status__in=[
                DecisionStatus.CANDIDATE,
                DecisionStatus.CONTACTED,
                DecisionStatus.BOUGHT,
                DecisionStatus.SOLD,
            ]
        ).count(),
        "contacted": Listing.objects.filter(
            decision_status__in=[
                DecisionStatus.CONTACTED,
                DecisionStatus.BOUGHT,
                DecisionStatus.SOLD,
            ]
        ).count(),
        "bought": Listing.objects.filter(
            decision_status__in=[DecisionStatus.BOUGHT, DecisionStatus.SOLD]
        ).count(),
        "sold": Listing.objects.filter(decision_status=DecisionStatus.SOLD).count(),
    }
    return counts


def ai_month_cost() -> str:
    from apps.analysis.services import ai_spend_summary

    return ai_spend_summary()["month_usd"]
