"""Deals HTML views: list, create/edit, CSV export."""

import csv
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.enums import AuditAction
from apps.core.exceptions import ApiError
from apps.core.permissions import is_administrator
from apps.core.services import enforce_rate_limit, record_audit
from apps.deals.enums import DealStatus
from apps.deals.forms import DealForm
from apps.deals.models import Deal
from apps.deals.services import compute_realized_profit, create_deal, update_deal
from apps.monitoring.models import Listing


def _admin_or_redirect(request: HttpRequest):
    if not is_administrator(request.user):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        return render(request, "403.html", status=403)
    return None


def deals_queryset(params: dict):
    qs = Deal.objects.select_related("listing").order_by("-purchased_at")
    status = params.get("status", "")
    if status:
        if status not in DealStatus.values:
            raise ValidationError({"status": ["Недопустимое значение."]})
        qs = qs.filter(status=status)
    model = params.get("model", "")
    if model:
        qs = qs.filter(listing__model_key=model)
    return qs


def deal_list(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    try:
        deals = deals_queryset(request.GET.dict())
        filter_error = None
    except ValidationError:
        deals = deals_queryset({})
        filter_error = "Недопустимые параметры фильтра; показаны все сделки."
    totals = {
        "invested": sum(
            (
                d.purchase_price_uah
                + d.acquisition_shipping_uah
                + d.repair_cost_uah
                + d.other_cost_uah
                for d in deals
                if d.status == DealStatus.IN_STOCK
            ),
            Decimal("0"),
        ),
        "realized": sum(
            (d.realized_profit_uah or Decimal("0") for d in deals if d.status == DealStatus.SOLD),
            Decimal("0"),
        ),
    }
    return render(
        request,
        "deals/deal_list.html",
        {"deals": deals, "totals": totals, "filter_error": filter_error},
    )


@require_http_methods(["GET", "POST"])
def deal_create(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    listing_id = request.GET.get("listing") or request.POST.get("listing")
    if not listing_id:
        messages.error(request, "Сделка создается из карточки объявления.")
        return redirect("listings:list")
    listing = get_object_or_404(Listing, pk=listing_id)

    initial = {"purchase_price_uah": listing.current_price_uah}
    form = DealForm(request.POST or None, initial=initial)
    # Status is fixed to IN_STOCK on creation.
    form.fields["status"].disabled = True
    form.fields["status"].initial = DealStatus.IN_STOCK

    if request.method == "POST" and form.is_valid():
        try:
            deal = create_deal(listing, form.cleaned_data, actor=request.user, request=request)
            messages.success(request, "Покупка сохранена, объявление помечено «Куплено».")
            if "save_and_open" in request.POST:
                return redirect("deals:edit", pk=deal.pk)
            return redirect("deals:list")
        except ApiError as exc:
            form.add_error(None, str(exc.detail))
    return render(request, "deals/deal_form.html", {"form": form, "listing": listing, "deal": None})


@require_http_methods(["GET", "POST"])
def deal_edit(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    deal = get_object_or_404(Deal.objects.select_related("listing"), pk=pk)
    form = DealForm(request.POST or None, instance=deal)
    if request.method == "POST" and form.is_valid():
        try:
            update_deal(
                deal,
                form.cleaned_data,
                expected_updated_at=request.POST.get("expected_updated_at"),
                actor=request.user,
                request=request,
            )
            messages.success(request, "Сделка обновлена.")
            return redirect("deals:list")
        except ApiError as exc:
            form.add_error(None, str(exc.detail))
    return render(
        request,
        "deals/deal_form.html",
        {
            "form": form,
            "listing": deal.listing,
            "deal": deal,
            "estimated_profit": compute_realized_profit(deal),
        },
    )


def _csv_safe(value: object) -> str:
    text = str(value if value is not None else "")
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def deal_export_csv(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    try:
        enforce_rate_limit(AuditAction.CSV_EXPORTED, "CSV_EXPORT", request.user)
    except ApiError as exc:
        messages.error(request, str(exc.detail))
        return redirect("deals:list")
    try:
        deals = deals_queryset(request.GET.dict())
    except ValidationError:
        return HttpResponse("Недопустимый фильтр.", status=400)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="deals.csv"'
    response.write("﻿")  # UTF-8 BOM для Excel/Numbers
    writer = csv.writer(response)
    writer.writerow(
        [
            "olx_id",
            "model",
            "status",
            "purchase_price_uah",
            "purchased_at",
            "shipping_uah",
            "repair_uah",
            "other_uah",
            "total_invested_uah",
            "sale_price_uah",
            "sold_at",
            "realized_profit_uah",
            "notes",
        ]
    )
    for deal in deals:
        total = (
            deal.purchase_price_uah
            + deal.acquisition_shipping_uah
            + deal.repair_cost_uah
            + deal.other_cost_uah
        )
        writer.writerow(
            [
                _csv_safe(deal.listing.olx_id),
                _csv_safe(deal.listing.model_key),
                _csv_safe(deal.status),
                _csv_safe(deal.purchase_price_uah),
                _csv_safe(deal.purchased_at.isoformat()),
                _csv_safe(deal.acquisition_shipping_uah),
                _csv_safe(deal.repair_cost_uah),
                _csv_safe(deal.other_cost_uah),
                _csv_safe(total),
                _csv_safe(deal.sale_price_uah),
                _csv_safe(deal.sold_at.isoformat() if deal.sold_at else ""),
                _csv_safe(deal.realized_profit_uah),
                _csv_safe(deal.notes[:200]),
            ]
        )
    record_audit(
        action=AuditAction.CSV_EXPORTED,
        actor=request.user,
        target_type="Deal",
        request=request,
    )
    return response
