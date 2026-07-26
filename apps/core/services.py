"""Core services: audit trail, DB-backed rate limits, runtime switches."""

import hashlib
import hmac
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.http import HttpRequest
from django.utils import timezone

from apps.core.enums import AuditAction
from apps.core.exceptions import ConflictError, RateLimitedError
from apps.core.logging import redact_mapping
from apps.core.models import AppState, AuditEvent

SAFETY_RESUME_COOLDOWN = timedelta(minutes=30)


def hash_ip(request: HttpRequest | None) -> str:
    if request is None:
        return ""
    ip = request.META.get("REMOTE_ADDR", "")
    if not ip:
        return ""
    return hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256).hexdigest()


def record_audit(
    *,
    action: str,
    actor: AbstractBaseUser | AnonymousUser | None = None,
    target_type: str = "",
    target_id: str = "",
    changes: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditEvent:
    actor_obj = actor if getattr(actor, "is_authenticated", False) else None
    request_id = getattr(request, "request_id", None) if request is not None else None
    return AuditEvent.objects.create(
        actor=actor_obj,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else "",
        changes=redact_mapping(changes or {}),
        request_id=request_id,
        ip_hash=hash_ip(request),
    )


def enforce_rate_limit(action: str, limit_key: str, actor: object = None) -> None:
    """Raise RateLimitedError when `action` happened too often in the window."""
    limit, window_seconds = settings.RATE_LIMITS[limit_key]
    since = timezone.now() - timedelta(seconds=window_seconds)
    queryset = AuditEvent.objects.filter(action=action, created_at__gte=since)
    if getattr(actor, "is_authenticated", False):
        queryset = queryset.filter(actor=actor)
    if queryset.count() >= limit:
        raise RateLimitedError(
            "Слишком много одинаковых действий. Подождите немного и повторите.",
            retry_after=window_seconds,
        )


def get_app_state() -> AppState:
    return AppState.get_solo()


def effective_monitoring(state: AppState | None = None) -> bool:
    state = state or get_app_state()
    if not settings.MONITOR_ENABLED:
        return False
    if state.monitoring_paused:
        return False
    if state.safety_block_until and state.safety_block_until > timezone.now():
        return False
    return True


def effective_ai(state: AppState | None = None) -> bool:
    state = state or get_app_state()
    return bool(settings.AI_ENABLED and state.ai_enabled and settings.OPENAI_API_KEY)


def pause_monitoring(reason: str, *, actor: object = None, request: HttpRequest | None = None) -> AppState:
    state = get_app_state()
    state.monitoring_paused = True
    state.pause_reason = reason[:255]
    state.save(update_fields=["monitoring_paused", "pause_reason", "updated_at"])
    record_audit(
        action=AuditAction.MONITORING_PAUSED,
        actor=actor,  # type: ignore[arg-type]
        target_type="AppState",
        target_id="1",
        changes={"reason": reason[:255]},
        request=request,
    )
    return state


def resume_monitoring(
    *,
    actor: object = None,
    request: HttpRequest | None = None,
    acknowledge_risk: bool = False,
) -> AppState:
    state = get_app_state()
    now = timezone.now()
    if state.safety_block_until and state.safety_block_until > now:
        raise ConflictError(
            "Защитная пауза после блокировки OLX еще действует. "
            "Дождитесь окончания и подтвердите риск."
        )
    if state.safety_ack_required and not acknowledge_risk:
        raise ConflictError(
            "Был инцидент CAPTCHA/блокировки. Для возобновления подтвердите риск "
            "(acknowledge_risk=true)."
        )
    state.monitoring_paused = False
    state.pause_reason = ""
    state.safety_ack_required = False
    state.safety_block_until = None
    state.safety_block_reason = ""
    state.save(
        update_fields=[
            "monitoring_paused",
            "pause_reason",
            "safety_ack_required",
            "safety_block_until",
            "safety_block_reason",
            "updated_at",
        ]
    )
    record_audit(
        action=AuditAction.MONITORING_RESUMED,
        actor=actor,  # type: ignore[arg-type]
        target_type="AppState",
        target_id="1",
        changes={"acknowledge_risk": acknowledge_risk},
        request=request,
    )
    return state


def apply_safety_block(reason: str, *, error_code: str) -> AppState:
    """Worker-triggered pause after CAPTCHA/403/429; requires manual acknowledge."""
    state = get_app_state()
    state.monitoring_paused = True
    state.pause_reason = reason[:255]
    state.safety_block_until = timezone.now() + SAFETY_RESUME_COOLDOWN
    state.safety_block_reason = error_code[:255]
    state.safety_ack_required = True
    state.save(
        update_fields=[
            "monitoring_paused",
            "pause_reason",
            "safety_block_until",
            "safety_block_reason",
            "safety_ack_required",
            "updated_at",
        ]
    )
    record_audit(
        action=AuditAction.WORKER_SAFETY_PAUSE,
        target_type="AppState",
        target_id="1",
        changes={"reason": reason[:255], "error_code": error_code},
    )
    return state


def worker_status(state: AppState | None = None) -> str:
    """HEALTHY / STALE / UNAVAILABLE / NEVER_RUN based on heartbeat age."""
    state = state or get_app_state()
    if state.worker_heartbeat_at is None:
        return "NEVER_RUN"
    age = (timezone.now() - state.worker_heartbeat_at).total_seconds()
    if age <= 90:
        return "HEALTHY"
    if age <= 180:
        return "STALE"
    return "UNAVAILABLE"
