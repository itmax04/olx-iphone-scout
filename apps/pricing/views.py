"""Pricing HTML views: market rules and defect reserves."""

from datetime import timedelta

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.enums import AuditAction
from apps.core.permissions import is_administrator
from apps.core.services import get_app_state, record_audit
from apps.pricing.forms import DefectReserveRuleForm, MarketPriceRuleForm
from apps.pricing.models import DefectReserveRule, MarketPriceRule


def _admin_or_redirect(request: HttpRequest):
    if not is_administrator(request.user):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        return render(request, "403.html", status=403)
    return None


def rules_list(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    stale_days = get_app_state().market_price_stale_days
    stale_cutoff = timezone.now() - timedelta(days=stale_days)
    market_rules = MarketPriceRule.objects.order_by("model_key", "storage_gb", "sim_variant")
    defect_rules = DefectReserveRule.objects.order_by("code", "model_key")
    return render(
        request,
        "pricing/rules_list.html",
        {
            "market_rules": market_rules,
            "defect_rules": defect_rules,
            "stale_cutoff": stale_cutoff,
            "stale_days": stale_days,
            "active_tab": request.GET.get("tab", "market"),
        },
    )


@require_http_methods(["GET", "POST"])
def market_rule_create(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    initial: dict[str, object] = {"checked_at": timezone.now()}
    copy_id = request.GET.get("copy")
    if copy_id:
        source = MarketPriceRule.objects.filter(pk=copy_id).first()
        if source:
            initial.update(
                {
                    "model_key": source.model_key,
                    "storage_gb": source.storage_gb,
                    "sim_variant": source.sim_variant,
                    "expected_final_sale_price_uah": source.expected_final_sale_price_uah,
                    "acquisition_shipping_uah": source.acquisition_shipping_uah,
                    "other_cost_reserve_uah": source.other_cost_reserve_uah,
                }
            )
    form = MarketPriceRuleForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        rule = form.save()
        record_audit(
            action=AuditAction.MARKET_RULE_CREATED,
            actor=request.user,
            target_type="MarketPriceRule",
            target_id=str(rule.id),
            request=request,
        )
        messages.success(request, "Рыночная цена сохранена.")
        return redirect("/prices/?tab=market")
    return render(request, "pricing/market_rule_form.html", {"form": form, "rule": None})


@require_http_methods(["GET", "POST"])
def market_rule_edit(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    rule = get_object_or_404(MarketPriceRule, pk=pk)
    form = MarketPriceRuleForm(request.POST or None, instance=rule)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit(
            action=AuditAction.MARKET_RULE_UPDATED,
            actor=request.user,
            target_type="MarketPriceRule",
            target_id=str(rule.id),
            request=request,
        )
        messages.success(request, "Изменения сохранены.")
        return redirect("/prices/?tab=market")
    return render(request, "pricing/market_rule_form.html", {"form": form, "rule": rule})


@require_http_methods(["POST"])
def market_rule_deactivate(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    rule = get_object_or_404(MarketPriceRule, pk=pk)
    rule.is_active = False
    rule.save(update_fields=["is_active", "updated_at"])
    record_audit(
        action=AuditAction.MARKET_RULE_DEACTIVATED,
        actor=request.user,
        target_type="MarketPriceRule",
        target_id=str(rule.id),
        request=request,
    )
    messages.success(request, "Правило деактивировано. Старые оценки не изменились.")
    return redirect("/prices/?tab=market")


@require_http_methods(["GET", "POST"])
def defect_rule_create(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    form = DefectReserveRuleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        rule = form.save()
        record_audit(
            action=AuditAction.DEFECT_RULE_CREATED,
            actor=request.user,
            target_type="DefectReserveRule",
            target_id=str(rule.id),
            request=request,
        )
        messages.success(request, "Резерв дефекта сохранен.")
        return redirect("/prices/?tab=defects")
    return render(request, "pricing/defect_rule_form.html", {"form": form, "rule": None})


@require_http_methods(["GET", "POST"])
def defect_rule_edit(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    rule = get_object_or_404(DefectReserveRule, pk=pk)
    form = DefectReserveRuleForm(request.POST or None, instance=rule)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit(
            action=AuditAction.DEFECT_RULE_UPDATED,
            actor=request.user,
            target_type="DefectReserveRule",
            target_id=str(rule.id),
            request=request,
        )
        messages.success(request, "Изменения сохранены.")
        return redirect("/prices/?tab=defects")
    return render(request, "pricing/defect_rule_form.html", {"form": form, "rule": rule})


@require_http_methods(["POST"])
def defect_rule_deactivate(request: HttpRequest, pk) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    rule = get_object_or_404(DefectReserveRule, pk=pk)
    rule.is_active = False
    rule.save(update_fields=["is_active", "updated_at"])
    record_audit(
        action=AuditAction.DEFECT_RULE_DEACTIVATED,
        actor=request.user,
        target_type="DefectReserveRule",
        target_id=str(rule.id),
        request=request,
    )
    messages.success(request, "Резерв деактивирован.")
    return redirect("/prices/?tab=defects")
