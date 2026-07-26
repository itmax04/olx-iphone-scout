"""Outbox event creation: fingerprints, safe payloads, dedupe."""

import hashlib
import logging
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from apps.alerts.enums import OutboxEventType
from apps.alerts.formatting import format_money
from apps.alerts.models import NotificationOutbox
from apps.monitoring.models import Listing

logger = logging.getLogger(__name__)


def _fingerprint(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _create_outbox(
    event_type: str, fingerprint: str, payload: dict, listing: Listing | None = None
) -> NotificationOutbox | None:
    try:
        return NotificationOutbox.objects.create(
            listing=listing,
            event_type=event_type,
            fingerprint=fingerprint,
            payload=payload,
            next_attempt_at=timezone.now(),
        )
    except IntegrityError:
        return None  # duplicate event, already queued/sent


def _listing_payload(listing: Listing) -> dict:
    from apps.analysis.selectors import latest_successful_analysis

    payload: dict = {
        "title": listing.title,
        "price": format_money(listing.current_price_uah),
        "sale_price": format_money(listing.current_expected_sale_price_uah),
        "reserve": format_money(listing.current_total_reserve_uah),
        "profit": format_money(listing.current_expected_profit_uah),
        "risk_level": listing.current_risk_level,
        "url": listing.canonical_url,
        "facts": [],
        "missing_checks": [],
        "seller_questions": [],
    }
    analysis = latest_successful_analysis(listing)
    if analysis is not None and analysis.result:
        result = analysis.result
        payload["ai_confidence"] = (
            f"{int(Decimal(str(analysis.confidence)) * 100)}%" if analysis.confidence else None
        )
        battery = result.get("battery_health", {})
        if isinstance(battery, dict) and battery.get("value"):
            payload["facts"].append(f"АКБ: продавец указал {battery['value']}%")
        for field, label in (
            ("face_id", "Face ID"),
            ("true_tone", "True Tone"),
            ("display_replacement", "Замена дисплея"),
        ):
            item = result.get(field, {})
            if isinstance(item, dict):
                status = item.get("status", "unknown")
                text = {"yes": "да", "no": "нет", "unknown": "не указано"}.get(status, status)
                payload["facts"].append(f"{label}: {text}")
        checks_map = {
            "face_id": "Face ID и True Tone",
            "true_tone": "True Tone",
            "icloud": "iCloud/MDM/блокировку оператора",
            "parts_history": "Историю деталей и обслуживания",
            "battery": "Состояние АКБ",
        }
        payload["missing_checks"] = [
            checks_map.get(item, item) for item in result.get("missing_checks", [])[:6]
        ]
        payload["seller_questions"] = list(result.get("seller_questions_uk", []))[:5]
    return payload


def enqueue_candidate_alert(listing: Listing, *, send: bool = True) -> NotificationOutbox | None:
    fingerprint = _fingerprint(
        OutboxEventType.NEW_CANDIDATE,
        listing.id,
        listing.current_price_uah,
        listing.content_hash,
    )
    payload = _listing_payload(listing)
    return _create_outbox(OutboxEventType.NEW_CANDIDATE, fingerprint, payload, listing)


def enqueue_price_drop_alert(
    listing: Listing, *, old_price: Decimal | None, send: bool = True
) -> NotificationOutbox | None:
    fingerprint = _fingerprint(
        OutboxEventType.PRICE_DROP,
        listing.id,
        listing.current_price_uah,  # fingerprint includes the NEW price (F-18)
        listing.content_hash,
    )
    payload = _listing_payload(listing)
    payload["old_price"] = format_money(old_price)
    return _create_outbox(OutboxEventType.PRICE_DROP, fingerprint, payload, listing)


def _incident_hour() -> str:
    return timezone.now().strftime("%Y-%m-%dT%H")


def enqueue_system_incident(error_code: str, message: str) -> NotificationOutbox | None:
    """Rate-limited by design: fingerprint includes the UTC hour."""
    event_type = (
        OutboxEventType.CAPTCHA if error_code == "OLX_CAPTCHA" else OutboxEventType.SYSTEM_ERROR
    )
    fingerprint = _fingerprint(event_type, error_code, _incident_hour())
    payload = {"error_code": error_code, "message": message[:500]}
    return _create_outbox(event_type, fingerprint, payload)


def enqueue_recovery(error_code: str, message: str = "") -> NotificationOutbox | None:
    fingerprint = _fingerprint(OutboxEventType.RECOVERED, error_code, _incident_hour())
    payload = {"error_code": error_code, "message": message[:500] or "Работа возобновлена."}
    return _create_outbox(OutboxEventType.RECOVERED, fingerprint, payload)


def enqueue_test_message() -> NotificationOutbox | None:
    now = timezone.now()
    fingerprint = _fingerprint(OutboxEventType.TEST, now.isoformat())
    payload = {
        "timestamp": now.strftime("%d.%m.%Y %H:%M:%S UTC"),
        "environment": settings.APP_ENV,
    }
    return _create_outbox(OutboxEventType.TEST, fingerprint, payload)
