"""Read-only analysis selectors."""

from apps.analysis.enums import AiStatus
from apps.analysis.models import AiAnalysis
from apps.monitoring.models import Listing


def latest_successful_analysis(listing: Listing) -> AiAnalysis | None:
    return (
        AiAnalysis.objects.filter(listing=listing, status=AiStatus.SUCCESS)
        .order_by("-created_at")
        .first()
    )


def running_analysis_exists(listing: Listing) -> bool:
    return AiAnalysis.objects.filter(
        listing=listing, status__in=[AiStatus.PENDING, AiStatus.RUNNING]
    ).exists()
