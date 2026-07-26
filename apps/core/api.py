"""Core JSON API: auth/me, dashboard, settings, system, integrations."""

import json
from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.http import HttpResponse
from rest_framework import serializers as drf_serializers
from rest_framework.views import APIView

from apps.core.api_helpers import data_response
from apps.core.enums import AuditAction
from apps.core.services import (
    enforce_rate_limit,
    get_app_state,
    pause_monitoring,
    record_audit,
    resume_monitoring,
)


class AuthMeApi(APIView):
    def get(self, request):
        return data_response(
            {
                "username": request.user.username,
                "email": request.user.email,
                "role": "Administrator",
            }
        )


class DashboardStatsApi(APIView):
    def get(self, request):
        period = request.query_params.get("period", "today")
        if period not in ("today", "7d", "30d", "month"):
            raise drf_serializers.ValidationError({"period": ["Недопустимое значение."]})
        from apps.core.services import worker_status
        from apps.dashboard.selectors import dashboard_stats

        stats = dashboard_stats(period)
        stats["worker_status"] = worker_status()
        return data_response(stats)


_SETTINGS_FIELDS = {
    "monitoring_paused",
    "pause_reason",
    "ai_enabled",
    "ai_escalation_confidence",
    "ai_high_value_profit_uah",
    "market_price_stale_days",
    "old_listing_refresh_hours",
    "scan_run_retention_days",
    "audit_retention_days",
}

_INT_BOUNDS = {
    "market_price_stale_days": (1, 30),
    "old_listing_refresh_hours": (1, 24),
    "scan_run_retention_days": (7, 365),
    "audit_retention_days": (30, 730),
}


def _settings_payload() -> dict:
    state = get_app_state()
    return {
        "monitoring_paused": state.monitoring_paused,
        "pause_reason": state.pause_reason,
        "ai_enabled": state.ai_enabled,
        "ai_escalation_confidence": str(state.ai_escalation_confidence),
        "ai_high_value_profit_uah": str(state.ai_high_value_profit_uah),
        "market_price_stale_days": state.market_price_stale_days,
        "old_listing_refresh_hours": state.old_listing_refresh_hours,
        "scan_run_retention_days": state.scan_run_retention_days,
        "audit_retention_days": state.audit_retention_days,
        "monitor_env_enabled": django_settings.MONITOR_ENABLED,
        "ai_env_enabled": django_settings.AI_ENABLED,
        "openai_configured": bool(django_settings.OPENAI_API_KEY),
        "telegram_configured": bool(
            django_settings.TELEGRAM_BOT_TOKEN and django_settings.TELEGRAM_CHAT_ID
        ),
        "openai_fast_model": django_settings.OPENAI_FAST_MODEL,
        "openai_deep_model": django_settings.OPENAI_DEEP_MODEL,
    }


class SettingsApi(APIView):
    def get(self, request):
        return data_response(_settings_payload())

    def patch(self, request):
        data = request.data
        if not isinstance(data, dict):
            raise drf_serializers.ValidationError({"non_field_errors": ["Ожидается объект."]})
        unknown = set(data.keys()) - _SETTINGS_FIELDS
        if unknown:
            raise drf_serializers.ValidationError(
                {field: ["Неизвестное поле."] for field in sorted(unknown)}
            )
        state = get_app_state()
        errors: dict[str, list[str]] = {}
        for field, value in data.items():
            if field in _INT_BOUNDS:
                low, high = _INT_BOUNDS[field]
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    errors[field] = ["Введите целое число."]
                    continue
                if not low <= value <= high:
                    errors[field] = [f"Допустимо от {low} до {high}."]
                    continue
                setattr(state, field, value)
            elif field == "ai_escalation_confidence":
                try:
                    decimal_value = Decimal(str(value))
                except InvalidOperation:
                    errors[field] = ["Введите число."]
                    continue
                if not Decimal("0") <= decimal_value <= Decimal("1"):
                    errors[field] = ["Допустимо от 0 до 1."]
                    continue
                state.ai_escalation_confidence = decimal_value
            elif field == "ai_high_value_profit_uah":
                try:
                    decimal_value = Decimal(str(value))
                except InvalidOperation:
                    errors[field] = ["Введите число."]
                    continue
                if decimal_value < 0:
                    errors[field] = ["Сумма не может быть отрицательной."]
                    continue
                state.ai_high_value_profit_uah = decimal_value
            elif field == "ai_enabled":
                state.ai_enabled = bool(value)
            elif field == "monitoring_paused":
                continue  # управляется pause/resume endpoint'ами
            elif field == "pause_reason":
                state.pause_reason = str(value)[:255]
        if errors:
            raise drf_serializers.ValidationError(errors)
        state.save()
        record_audit(
            action=AuditAction.SETTINGS_UPDATED,
            actor=request.user,
            target_type="AppState",
            target_id="1",
            changes={k: str(v) for k, v in data.items()},
            request=request,
        )
        return data_response(_settings_payload())


class SystemStatusApi(APIView):
    def get(self, request):
        from apps.core.system import system_status_data

        return data_response(system_status_data())


class SystemPauseApi(APIView):
    def post(self, request):
        reason = str(request.data.get("reason", "") or "")
        if len(reason) > 255:
            raise drf_serializers.ValidationError({"reason": ["Максимум 255 символов."]})
        pause_monitoring(reason or "Пауза через API", actor=request.user, request=request)
        return data_response({"monitoring_paused": True})


class SystemResumeApi(APIView):
    def post(self, request):
        resume_monitoring(
            actor=request.user,
            request=request,
            acknowledge_risk=bool(request.data.get("acknowledge_risk", False)),
        )
        return data_response({"monitoring_paused": False})


class TelegramTestApi(APIView):
    def post(self, request):
        from apps.core.integrations import send_telegram_test

        return data_response(send_telegram_test(actor=request.user, request=request))


class OpenAiCheckApi(APIView):
    def post(self, request):
        from apps.core.integrations import check_openai_configuration

        return data_response(check_openai_configuration(actor=request.user, request=request))


class CleanupPreviewApi(APIView):
    def post(self, request):
        from apps.core.cleanup import cleanup_counts

        enforce_rate_limit(AuditAction.CLEANUP_PREVIEWED, "CLEANUP_PREVIEW", request.user)
        counts = cleanup_counts()
        record_audit(
            action=AuditAction.CLEANUP_PREVIEWED,
            actor=request.user,
            target_type="AppState",
            request=request,
        )
        return data_response(counts)


class SystemDiagnosticApi(APIView):
    def get(self, request):
        from apps.core.system import system_status_data

        payload = system_status_data()
        response = HttpResponse(
            json.dumps({"data": payload}, ensure_ascii=False, indent=2),
            content_type="application/json",
        )
        response["Content-Disposition"] = 'attachment; filename="system-diagnostic.json"'
        return response
