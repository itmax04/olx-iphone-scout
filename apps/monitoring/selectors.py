"""Read-only monitoring selectors with allow-listed filters and sorts."""

from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet

from apps.monitoring.enums import DecisionStatus, RiskLevel, SellerType
from apps.monitoring.models import Listing, ScanRun, SearchProfile

LISTING_SORTS = {
    "new": "-first_seen_at",
    "updated": "-updated_at",
    "price_asc": "current_price_uah",
    "price_desc": "-current_price_uah",
    "profit": "-current_expected_profit_uah",
    "risk": "-current_risk_level",
}


def search_profiles_queryset(params: dict) -> QuerySet[SearchProfile]:
    qs = SearchProfile.objects.all()
    status = params.get("status", "all")
    if status == "active":
        qs = qs.filter(is_active=True, archived_at__isnull=True)
    elif status == "paused":
        qs = qs.filter(is_active=False, archived_at__isnull=True)
    elif status == "error":
        qs = qs.filter(consecutive_failures__gt=0, archived_at__isnull=True)
    elif status == "archived":
        qs = qs.filter(archived_at__isnull=False)
    elif status == "all":
        qs = qs.filter(archived_at__isnull=True)
    else:
        raise ValidationError({"status": ["Недопустимое значение."]})
    model = params.get("model", "")
    if model:
        qs = qs.filter(target_models__contains=model)
    q = params.get("q", "")
    if q:
        qs = qs.filter(name__icontains=q[:80])
    return qs.order_by("name")


def listings_queryset(params: dict) -> QuerySet[Listing]:
    qs = Listing.objects.all()

    q = params.get("q", "")
    if q:
        qs = qs.filter(Q(title__icontains=q[:100]) | Q(olx_id__icontains=q[:64]))
    model = params.get("model", "")
    if model:
        qs = qs.filter(model_key=model)
    storage = params.get("storage", "")
    if storage:
        if not storage.isdigit():
            raise ValidationError({"storage": ["Недопустимое значение."]})
        qs = qs.filter(storage_gb=int(storage))
    for bound, field in (
        ("price_min", "current_price_uah__gte"),
        ("price_max", "current_price_uah__lte"),
    ):
        raw = params.get(bound, "")
        if raw:
            try:
                qs = qs.filter(**{field: raw})
            except (ValueError, ValidationError):
                raise ValidationError({bound: ["Введите число."]})
    profit_min = params.get("profit_min", "")
    if profit_min:
        try:
            qs = qs.filter(current_expected_profit_uah__gte=profit_min)
        except (ValueError, ValidationError):
            raise ValidationError({"profit_min": ["Введите число."]})
    risk = params.get("risk", "")
    if risk:
        if risk not in RiskLevel.values:
            raise ValidationError({"risk": ["Недопустимое значение."]})
        qs = qs.filter(current_risk_level=risk)
    status = params.get("status", "")
    if status:
        if status not in DecisionStatus.values:
            raise ValidationError({"status": ["Недопустимое значение."]})
        qs = qs.filter(decision_status=status)
    profile = params.get("profile", "")
    if profile:
        qs = qs.filter(discoveries__search_profile_id=profile)
    seller = params.get("seller", "")
    if seller:
        if seller not in SellerType.values:
            raise ValidationError({"seller": ["Недопустимое значение."]})
        qs = qs.filter(seller_type=seller)
    delivery = params.get("delivery", "")
    if delivery == "yes":
        qs = qs.filter(delivery_available=True)
    elif delivery == "no":
        qs = qs.filter(delivery_available=False)
    elif delivery == "unknown":
        qs = qs.filter(delivery_available__isnull=True)
    elif delivery:
        raise ValidationError({"delivery": ["Недопустимое значение."]})
    if params.get("candidate") in ("1", "true", "True"):
        qs = qs.filter(current_is_candidate=True)
    if params.get("manual_review") in ("1", "true"):
        qs = qs.filter(current_evaluation__decision="MANUAL_REVIEW", current_is_candidate=False)
    active = params.get("active", "")
    if active == "1":
        qs = qs.filter(is_active=True)
    elif active == "0":
        qs = qs.filter(is_active=False)

    sort = params.get("sort", "new")
    if sort not in LISTING_SORTS:
        raise ValidationError({"sort": ["Недопустимая сортировка."]})
    return qs.select_related("current_evaluation").order_by(LISTING_SORTS[sort], "-id").distinct()


def scan_runs_queryset(params: dict) -> QuerySet[ScanRun]:
    qs = ScanRun.objects.select_related("search_profile")
    profile = params.get("profile", "")
    if profile:
        qs = qs.filter(search_profile_id=profile)
    status = params.get("status", "")
    if status:
        if status == "failed":
            qs = qs.filter(status__in=["FAILED", "BLOCKED"])
        elif status in ("RUNNING", "SUCCESS", "PARTIAL", "FAILED", "BLOCKED"):
            qs = qs.filter(status=status)
        else:
            raise ValidationError({"status": ["Недопустимое значение."]})
    error_code = params.get("error_code", "")
    if error_code:
        qs = qs.filter(error_code=error_code[:64])
    return qs.order_by("-started_at")
