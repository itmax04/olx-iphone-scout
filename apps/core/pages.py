"""Core HTML pages: settings and system diagnostics."""

from django import forms
from django.conf import settings as django_settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.enums import AuditAction
from apps.core.exceptions import ApiError
from apps.core.models import AppState
from apps.core.permissions import is_administrator
from apps.core.services import (
    get_app_state,
    pause_monitoring,
    record_audit,
    resume_monitoring,
)


def _admin_or_redirect(request: HttpRequest):
    if not is_administrator(request.user):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        return render(request, "403.html", status=403)
    return None


class AppSettingsForm(forms.ModelForm):
    class Meta:
        model = AppState
        fields = [
            "ai_enabled",
            "ai_escalation_confidence",
            "ai_high_value_profit_uah",
            "market_price_stale_days",
            "old_listing_refresh_hours",
            "scan_run_retention_days",
            "audit_retention_days",
        ]
        labels = {
            "ai_enabled": "AI-анализ включен (работает только при AI_ENABLED=true в окружении)",
            "ai_escalation_confidence": "Порог уверенности для deep AI (0–1)",
            "ai_high_value_profit_uah": "Порог «особо выгодно», грн",
            "market_price_stale_days": "Актуальность рыночной цены, дней (1–30)",
            "old_listing_refresh_hours": "Перепроверка старых объявлений, часов (1–24)",
            "scan_run_retention_days": "Хранить журнал запусков, дней (7–365)",
            "audit_retention_days": "Хранить аудит, дней (30–730)",
        }
        widgets = {
            "ai_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ai_escalation_confidence": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.001", "min": "0", "max": "1"}
            ),
            "ai_high_value_profit_uah": forms.NumberInput(
                attrs={"class": "form-control", "min": "0"}
            ),
            "market_price_stale_days": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "max": "30"}
            ),
            "old_listing_refresh_hours": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "max": "24"}
            ),
            "scan_run_retention_days": forms.NumberInput(
                attrs={"class": "form-control", "min": "7", "max": "365"}
            ),
            "audit_retention_days": forms.NumberInput(
                attrs={"class": "form-control", "min": "30", "max": "730"}
            ),
        }


@require_http_methods(["GET", "POST"])
def settings_page(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    state = get_app_state()
    form = AppSettingsForm(request.POST or None, instance=state)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit(
            action=AuditAction.SETTINGS_UPDATED,
            actor=request.user,
            target_type="AppState",
            target_id="1",
            changes={k: str(v) for k, v in form.cleaned_data.items()},
            request=request,
        )
        messages.success(request, "Настройки сохранены.")
        return redirect("app_settings:index")
    integrations = {
        "openai_configured": bool(django_settings.OPENAI_API_KEY),
        "telegram_configured": bool(
            django_settings.TELEGRAM_BOT_TOKEN and django_settings.TELEGRAM_CHAT_ID
        ),
        "fast_model": django_settings.OPENAI_FAST_MODEL,
        "deep_model": django_settings.OPENAI_DEEP_MODEL,
        "ai_env_enabled": django_settings.AI_ENABLED,
        "monitor_env_enabled": django_settings.MONITOR_ENABLED,
    }
    return render(
        request,
        "core/settings.html",
        {"form": form, "state": state, "integrations": integrations},
    )


def system_page(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    from apps.core.system import system_status_data

    return render(request, "core/system_status.html", {"data": system_status_data()})


@require_http_methods(["POST"])
def pause_page_action(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    reason = (request.POST.get("reason") or "Ручная пауза")[:255]
    pause_monitoring(reason, actor=request.user, request=request)
    messages.success(request, "Мониторинг приостановлен.")
    return redirect(request.POST.get("next") or "dashboard:index")


@require_http_methods(["POST"])
def resume_page_action(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    try:
        resume_monitoring(
            actor=request.user,
            request=request,
            acknowledge_risk=request.POST.get("acknowledge_risk") == "1",
        )
        messages.success(request, "Мониторинг возобновлен.")
    except ApiError as exc:
        messages.error(request, str(exc.detail))
    return redirect(request.POST.get("next") or "dashboard:index")


@require_http_methods(["POST"])
def telegram_test_action(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    from apps.core.integrations import send_telegram_test

    try:
        send_telegram_test(actor=request.user, request=request)
        messages.success(request, "Тестовое сообщение отправлено в Telegram.")
    except ApiError as exc:
        messages.error(request, str(exc.detail))
    return redirect(request.POST.get("next") or "app_settings:index")


@require_http_methods(["POST"])
def openai_check_action(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    from apps.core.integrations import check_openai_configuration

    try:
        result = check_openai_configuration(actor=request.user, request=request)
        messages.success(
            request,
            f"Конфигурация OpenAI: {'настроена' if result['configured'] else 'неполная'} "
            f"(fast: {result['fast_model']}, deep: {result['deep_model']}); provider не вызывался.",
        )
    except ApiError as exc:
        messages.error(request, str(exc.detail))
    return redirect(request.POST.get("next") or "app_settings:index")


@require_http_methods(["POST"])
def cleanup_preview_action(request: HttpRequest) -> HttpResponse:
    guard = _admin_or_redirect(request)
    if guard:
        return guard
    from apps.core.cleanup import cleanup_counts
    from apps.core.services import enforce_rate_limit

    try:
        enforce_rate_limit(AuditAction.CLEANUP_PREVIEWED, "CLEANUP_PREVIEW", request.user)
        counts = cleanup_counts()
        record_audit(
            action=AuditAction.CLEANUP_PREVIEWED,
            actor=request.user,
            target_type="AppState",
            request=request,
        )
        messages.info(
            request,
            f"Очистка (dry run): запусков {counts['scan_runs']}, аудита {counts['audit_events']}, "
            f"axes {counts['axes_logs']}, сессий {counts['sessions']}. Удаление — только через CLI "
            "cleanup_old_data --confirm.",
        )
    except ApiError as exc:
        messages.error(request, str(exc.detail))
    return redirect("system:index")
