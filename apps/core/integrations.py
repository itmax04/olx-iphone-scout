"""Integration actions shared by HTML pages and the JSON API."""

from django.conf import settings

from apps.core.enums import AuditAction
from apps.core.exceptions import (
    PreconditionError,
    ServiceUnavailableError,
)
from apps.core.services import enforce_rate_limit, record_audit


def send_telegram_test(*, actor=None, request=None) -> dict:
    from apps.alerts.client import TelegramError, TelegramNotConfigured, get_client
    from apps.alerts.enums import OutboxStatus
    from apps.alerts.formatting import render_message
    from apps.alerts.services import enqueue_test_message

    enforce_rate_limit(AuditAction.TELEGRAM_TEST_SENT, "TELEGRAM_TEST", actor)
    client = get_client()
    if not client.configured:
        raise PreconditionError(
            "Telegram не настроен: заполните TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID."
        )
    item = enqueue_test_message()
    text = render_message("TEST", item.payload if item else {})
    try:
        message_id = client.send_message(text)
    except TelegramNotConfigured:
        raise PreconditionError("Telegram не настроен.")
    except TelegramError as exc:
        if item is not None:
            item.status = OutboxStatus.FAILED
            item.last_error_message = str(exc)[:500]
            item.save(update_fields=["status", "last_error_message", "updated_at"])
        raise ServiceUnavailableError("Telegram временно недоступен. Попробуйте позже.")
    if item is not None:
        from django.utils import timezone

        item.status = OutboxStatus.SENT
        item.telegram_message_id = message_id
        item.sent_at = timezone.now()
        item.save(update_fields=["status", "telegram_message_id", "sent_at", "updated_at"])
    record_audit(
        action=AuditAction.TELEGRAM_TEST_SENT, actor=actor, target_type="Telegram", request=request
    )
    return {"sent": True}


def check_openai_configuration(*, actor=None, request=None) -> dict:
    """Local-only config check; the provider is never called."""
    enforce_rate_limit(AuditAction.OPENAI_CONFIG_CHECKED, "OPENAI_CHECK", actor)
    configured = bool(
        settings.OPENAI_API_KEY
        and settings.OPENAI_FAST_MODEL
        and settings.OPENAI_DEEP_MODEL
        and settings.OPENAI_REASONING_EFFORT in ("minimal", "low", "medium", "high")
        and settings.AI_DAILY_HARD_LIMIT_USD > 0
        and settings.AI_MONTHLY_HARD_LIMIT_USD > 0
    )
    record_audit(
        action=AuditAction.OPENAI_CONFIG_CHECKED, actor=actor, target_type="OpenAI", request=request
    )
    result = {
        "configured": configured,
        "fast_model": settings.OPENAI_FAST_MODEL,
        "deep_model": settings.OPENAI_DEEP_MODEL,
        "provider_called": False,
    }
    if not configured:
        raise PreconditionError(
            "Конфигурация OpenAI неполна: проверьте OPENAI_API_KEY, model IDs, "
            "OPENAI_REASONING_EFFORT и лимиты расходов."
        )
    return result
