"""Monitoring HTML views: searches, listings, runs."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.enums import AuditAction
from apps.core.exceptions import ApiError
from apps.core.permissions import is_administrator
from apps.core.services import record_audit
from apps.monitoring.forms import SearchProfileForm
from apps.monitoring.models import Listing, SearchProfile
from apps.monitoring.selectors import (
    listings_queryset,
    scan_runs_queryset,
    search_profiles_queryset,
)
from apps.monitoring.status_machine import change_status
from apps.pricing.constants import MODEL_CHOICES, model_label


def _admin_or_redirect(request: HttpRequest):
    if not is_administrator(request.user):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        return render(request, "403.html", status=403)
    return None


def _query_string(request: HttpRequest) -> str:
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


# ---------- Searches ----------


def search_list(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    try:
        profiles = search_profiles_queryset(request.GET.dict())
    except ValidationError:
        messages.error(request, "Недопустимые параметры фильтра; показаны все профили.")
        profiles = search_profiles_queryset({})
    return render(
        request,
        "monitoring/search_list.html",
        {
            "profiles": profiles,
            "model_choices": MODEL_CHOICES,
            "status_filter": request.GET.get("status", "all"),
        },
    )


@require_http_methods(["GET", "POST"])
def search_create(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    form = SearchProfileForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.created_by = request.user
        profile.save()
        record_audit(
            action=AuditAction.SEARCH_PROFILE_CREATED,
            actor=request.user,
            target_type="SearchProfile",
            target_id=str(profile.id),
            request=request,
        )
        messages.success(request, f"Поиск «{profile.name}» создан.")
        if "save_and_run" in request.POST:
            return _run_now_redirect(request, profile)
        return redirect("searches:list")
    return render(request, "monitoring/search_form.html", {"form": form, "profile": None})


@require_http_methods(["GET", "POST"])
def search_edit(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    profile = get_object_or_404(SearchProfile, pk=pk)
    form = SearchProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit(
            action=AuditAction.SEARCH_PROFILE_UPDATED,
            actor=request.user,
            target_type="SearchProfile",
            target_id=str(profile.id),
            request=request,
        )
        messages.success(request, "Изменения сохранены.")
        if "save_and_run" in request.POST:
            return _run_now_redirect(request, profile)
        return redirect("searches:list")
    return render(request, "monitoring/search_form.html", {"form": form, "profile": profile})


def _run_now_redirect(request: HttpRequest, profile: SearchProfile) -> HttpResponse:
    from apps.monitoring.services import queue_manual_run

    try:
        queue_manual_run(profile, actor=request.user, request=request)
        messages.success(request, "Поставлено в очередь: worker выполнит скан.")
    except ApiError as exc:
        messages.error(request, str(exc.detail))
    return redirect("searches:list")


@require_http_methods(["POST"])
def search_run_now(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    profile = get_object_or_404(SearchProfile, pk=pk)
    return _run_now_redirect(request, profile)


@require_http_methods(["POST"])
def search_toggle(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    profile = get_object_or_404(SearchProfile, pk=pk, archived_at__isnull=True)
    profile.is_active = not profile.is_active
    profile.save(update_fields=["is_active", "updated_at"])
    record_audit(
        action=AuditAction.SEARCH_PROFILE_UPDATED,
        actor=request.user,
        target_type="SearchProfile",
        target_id=str(profile.id),
        changes={"is_active": profile.is_active},
        request=request,
    )
    messages.success(
        request, f"Поиск «{profile.name}» {'включен' if profile.is_active else 'на паузе'}."
    )
    return redirect("searches:list")


@require_http_methods(["POST"])
def search_archive(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    profile = get_object_or_404(SearchProfile, pk=pk)
    from apps.monitoring.services import archive_profile

    try:
        archive_profile(profile, actor=request.user, request=request)
        messages.success(request, f"Поиск «{profile.name}» архивирован. История сохранена.")
    except ApiError as exc:
        messages.error(request, str(exc.detail))
    return redirect("searches:list")


@require_http_methods(["POST"])
def search_test_url(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    from apps.monitoring.services import test_search_url

    url = request.POST.get("olx_url", "")
    context: dict = {}
    try:
        context["test_result"] = test_search_url(url, actor=request.user, request=request)
    except ValidationError as exc:
        context["test_error"] = "; ".join(exc.messages)
    except ApiError as exc:
        context["test_error"] = str(exc.detail)
    except Exception as exc:
        from apps.monitoring.collectors.exceptions import CollectorError

        if isinstance(exc, CollectorError):
            context["test_error"] = exc.safe_message
        else:
            context["test_error"] = "Не удалось проверить URL."
    return render(request, "monitoring/partials/url_test_result.html", context)


# ---------- Listings ----------


def listing_list(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    params = request.GET.dict()
    try:
        qs = listings_queryset(params)
        filter_error = None
    except ValidationError:
        qs = listings_queryset({})
        filter_error = "Недопустимые параметры фильтра; показаны все объявления."
    try:
        page_size = min(max(int(params.get("page_size", 25)), 1), 100)
    except ValueError:
        page_size = 25
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(params.get("page", 1))
    return render(
        request,
        "monitoring/listing_list.html",
        {
            "page_obj": page_obj,
            "query_string": _query_string(request),
            "model_choices": MODEL_CHOICES,
            "filter_error": filter_error,
            "has_filters": bool(_query_string(request)),
        },
    )


def listing_detail(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    listing = get_object_or_404(
        Listing.objects.select_related("current_evaluation__search_profile"), pk=pk
    )
    from apps.analysis.selectors import latest_successful_analysis

    snapshots = listing.snapshots.order_by("-observed_at")[:30]
    evaluations = listing.evaluations.select_related("search_profile").order_by("-created_at")[:20]
    analysis = latest_successful_analysis(listing)
    alerts = listing.outbox_items.order_by("-created_at")[:20]
    deal = getattr(listing, "deal", None)
    return render(
        request,
        "monitoring/listing_detail.html",
        {
            "listing": listing,
            "snapshots": snapshots,
            "evaluations": evaluations,
            "analysis": analysis,
            "analysis_result": analysis.result if analysis else None,
            "alerts": alerts,
            "deal": deal,
            "model_label": model_label(listing.model_key) if listing.model_key else "",
            "discoveries": listing.discoveries.select_related("search_profile"),
        },
    )


@require_http_methods(["POST"])
def listing_set_status(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    listing = get_object_or_404(Listing, pk=pk)
    new_status = request.POST.get("status") or None
    note = request.POST.get("note")
    expected = request.POST.get("expected_current_status") or None
    try:
        change_status(
            listing,
            new_status=new_status,
            note=note,
            expected_current_status=expected,
            actor=request.user,
            request=request,
        )
        messages.success(request, "Сохранено.")
    except ApiError as exc:
        messages.error(request, str(exc.detail))
    return redirect("listings:detail", pk=pk)


@require_http_methods(["POST"])
def listing_reanalyze(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    listing = get_object_or_404(Listing, pk=pk)
    from apps.analysis.services import AiAlreadyRunning, request_reanalysis
    from apps.core.services import effective_ai, enforce_rate_limit

    if not effective_ai():
        messages.error(request, "AI выключен или не настроен (AI_ENABLED, OPENAI_API_KEY).")
        return redirect("listings:detail", pk=pk)
    if not listing.is_active:
        messages.error(request, "Объявление неактивно; анализ не запущен.")
        return redirect("listings:detail", pk=pk)
    force = request.POST.get("force") == "1"
    reason = (request.POST.get("reason") or "").strip()
    try:
        enforce_rate_limit(AuditAction.REANALYZE_REQUESTED, "REANALYZE", request.user)
        result = request_reanalysis(listing, force=force, force_reason=reason)
        record_audit(
            action=AuditAction.REANALYZE_REQUESTED,
            actor=request.user,
            target_type="Listing",
            target_id=str(listing.id),
            changes={"force": force, "cache_hit": result["cache_hit"]},
            request=request,
        )
        if result["cache_hit"]:
            messages.success(request, "Результат уже есть: использован кеш анализа.")
        else:
            messages.success(request, "Поставлено в очередь: worker выполнит анализ.")
    except AiAlreadyRunning:
        messages.error(request, "Анализ уже выполняется.")
    except ValueError as exc:
        messages.error(request, str(exc))
    except ApiError as exc:
        messages.error(request, str(exc.detail))
    return redirect("listings:detail", pk=pk)


# ---------- Runs ----------


def run_list(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    try:
        qs = scan_runs_queryset(request.GET.dict())
        filter_error = None
    except ValidationError:
        qs = scan_runs_queryset({})
        filter_error = "Недопустимые параметры фильтра; показаны все запуски."
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    profiles = SearchProfile.objects.filter(archived_at__isnull=True).order_by("name")
    return render(
        request,
        "monitoring/run_list.html",
        {
            "page_obj": page_obj,
            "query_string": _query_string(request),
            "profiles": profiles,
            "filter_error": filter_error,
        },
    )
