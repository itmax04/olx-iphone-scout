"""Outbox delivery loop: DB row first, then Telegram; bounded retries."""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.alerts.client import TelegramClient, TelegramError, get_client
from apps.alerts.enums import OutboxStatus
from apps.alerts.formatting import render_message
from apps.alerts.models import NotificationOutbox

logger = logging.getLogger(__name__)

# Retry ladder (§6.9): 15s, 60s, 5m, 15m, 1h. After 5 attempts -> FAILED.
RETRY_DELAYS_SECONDS = (15, 60, 300, 900, 3600)
MAX_ATTEMPTS = 5
STALE_SENDING_MINUTES = 10
BATCH_SIZE = 10


def recover_stale_sending() -> int:
    cutoff = timezone.now() - timedelta(minutes=STALE_SENDING_MINUTES)
    return NotificationOutbox.objects.filter(
        status=OutboxStatus.SENDING, locked_at__lt=cutoff
    ).update(status=OutboxStatus.PENDING, locked_at=None)


def _claim_batch() -> list[NotificationOutbox]:
    now = timezone.now()
    with transaction.atomic():
        rows = list(
            NotificationOutbox.objects.select_for_update(skip_locked=True)
            .filter(status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY], next_attempt_at__lte=now)
            .order_by("next_attempt_at")[:BATCH_SIZE]
        )
        for row in rows:
            row.status = OutboxStatus.SENDING
            row.locked_at = now
            row.save(update_fields=["status", "locked_at", "updated_at"])
    return rows


def _mark_sent(item: NotificationOutbox, message_id: str) -> None:
    item.status = OutboxStatus.SENT
    item.telegram_message_id = message_id
    item.sent_at = timezone.now()
    item.locked_at = None
    item.last_error_code = ""
    item.last_error_message = ""
    item.save(
        update_fields=[
            "status",
            "telegram_message_id",
            "sent_at",
            "locked_at",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )


def _mark_failure(item: NotificationOutbox, error: TelegramError) -> None:
    item.attempts += 1
    item.locked_at = None
    item.last_error_code = f"HTTP_{error.status_code}" if error.status_code else "NETWORK"
    item.last_error_message = str(error)[:500]
    if error.permanent or item.attempts >= MAX_ATTEMPTS:
        item.status = OutboxStatus.FAILED
    else:
        item.status = OutboxStatus.RETRY
        if error.retry_after is not None:
            delay = max(error.retry_after, 1)
        else:
            delay = RETRY_DELAYS_SECONDS[min(item.attempts - 1, len(RETRY_DELAYS_SECONDS) - 1)]
        item.next_attempt_at = timezone.now() + timedelta(seconds=delay)
    item.save(
        update_fields=[
            "status",
            "attempts",
            "locked_at",
            "next_attempt_at",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )


def process_outbox_batch(client: TelegramClient | None = None) -> int:
    """Send due outbox rows. Returns the number of successfully sent rows."""
    recover_stale_sending()
    client = client or get_client()
    if not client.configured:
        return 0
    sent = 0
    for item in _claim_batch():
        text = render_message(item.event_type, item.payload or {})
        url = (item.payload or {}).get("url", "")
        button = ("Открыть OLX", url) if url.startswith("https://") else None
        try:
            message_id = client.send_message(text, url_button=button)
        except TelegramError as exc:
            _mark_failure(item, exc)
            logger.warning(
                "outbox_send_failed",
                extra={
                    "event": "outbox_send_failed",
                    "outbox_id": str(item.id),
                    "error_code": item.last_error_code,
                },
            )
            continue
        _mark_sent(item, message_id)
        sent += 1
        logger.info(
            "outbox_sent", extra={"event": "outbox_sent", "outbox_id": str(item.id)}
        )
    return sent
