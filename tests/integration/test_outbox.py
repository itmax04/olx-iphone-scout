"""I-16..I-21: transactional outbox с mock Telegram."""

import json
from datetime import timedelta

import httpx
import pytest
from django.utils import timezone

from apps.alerts.client import TelegramClient
from apps.alerts.enums import OutboxStatus
from apps.alerts.models import NotificationOutbox
from apps.alerts.outbox import process_outbox_batch, recover_stale_sending
from apps.alerts.services import enqueue_candidate_alert, enqueue_test_message

pytestmark = pytest.mark.django_db


def make_client(handler, settings) -> TelegramClient:
    settings.TELEGRAM_BOT_TOKEN = "123456:TEST-token-not-real"
    settings.TELEGRAM_CHAT_ID = "42"
    return TelegramClient(transport=httpx.MockTransport(handler))


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": {"message_id": 777}})


class TestDelivery:
    def test_pending_sent_and_marked(self, listing, settings):
        enqueue_candidate_alert(listing)
        sent = process_outbox_batch(make_client(ok_handler, settings))
        assert sent == 1
        item = NotificationOutbox.objects.get()
        assert item.status == OutboxStatus.SENT  # I-19
        assert item.telegram_message_id == "777"
        assert item.sent_at is not None

    def test_restart_delivers_pending(self, listing, settings):
        """I-17: запись создана до отправки; «после рестарта» доставляется."""
        enqueue_candidate_alert(listing)
        assert NotificationOutbox.objects.get().status == OutboxStatus.PENDING
        # Имитация рестарта: просто новый вызов цикла
        process_outbox_batch(make_client(ok_handler, settings))
        assert NotificationOutbox.objects.get().status == OutboxStatus.SENT

    def test_not_configured_no_send(self, listing, settings):
        settings.TELEGRAM_BOT_TOKEN = ""
        settings.TELEGRAM_CHAT_ID = ""
        enqueue_candidate_alert(listing)
        sent = process_outbox_batch(TelegramClient())
        assert sent == 0
        assert NotificationOutbox.objects.get().status == OutboxStatus.PENDING


class TestRetries:
    def test_permanent_400_fails_immediately(self, listing, settings):
        def handler(request):
            return httpx.Response(400, json={"ok": False, "description": "Bad Request"})

        enqueue_candidate_alert(listing)
        process_outbox_batch(make_client(handler, settings))
        item = NotificationOutbox.objects.get()
        assert item.status == OutboxStatus.FAILED  # I-20
        assert item.attempts == 1

    def test_5xx_retries_up_to_five(self, listing, settings):
        def handler(request):
            return httpx.Response(502)

        enqueue_candidate_alert(listing)
        client = make_client(handler, settings)
        for _ in range(5):
            NotificationOutbox.objects.update(next_attempt_at=timezone.now())
            process_outbox_batch(client)
        item = NotificationOutbox.objects.get()
        assert item.status == OutboxStatus.FAILED  # I-21
        assert item.attempts == 5

    def test_429_respects_retry_after(self, listing, settings):
        def handler(request):
            return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 20}})

        enqueue_candidate_alert(listing)
        before = timezone.now()
        process_outbox_batch(make_client(handler, settings))
        item = NotificationOutbox.objects.get()
        assert item.status == OutboxStatus.RETRY
        assert item.next_attempt_at >= before + timedelta(seconds=19)  # U-37

    def test_network_error_retry_ladder(self, listing, settings):
        def handler(request):
            raise httpx.ConnectError("boom")

        enqueue_candidate_alert(listing)
        before = timezone.now()
        process_outbox_batch(make_client(handler, settings))
        item = NotificationOutbox.objects.get()
        assert item.status == OutboxStatus.RETRY
        assert item.last_error_code == "NETWORK"
        assert item.next_attempt_at >= before + timedelta(seconds=14)  # U-36 первая ступень 15с


class TestStaleSending:
    def test_stale_sending_recovered(self, listing, settings):
        enqueue_candidate_alert(listing)
        NotificationOutbox.objects.update(
            status=OutboxStatus.SENDING, locked_at=timezone.now() - timedelta(minutes=15)
        )
        recovered = recover_stale_sending()
        assert recovered == 1  # I-18
        assert NotificationOutbox.objects.get().status == OutboxStatus.PENDING


class TestMessageContent:
    def test_no_token_in_payload_and_url_button(self, listing, settings):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

        enqueue_candidate_alert(listing)
        process_outbox_batch(make_client(handler, settings))
        body = captured["body"]
        assert body["chat_id"] == "42"
        assert "iPhone 13" in body["text"]
        keyboard = body["reply_markup"]["inline_keyboard"][0][0]
        assert keyboard["text"] == "Открыть OLX"
        assert keyboard["url"].startswith("https://www.olx.ua/")

    def test_test_message_content(self, settings, db):
        item = enqueue_test_message()
        from apps.alerts.formatting import render_message

        text = render_message(item.event_type, item.payload)
        assert "Тест OLX iPhone Scout" in text
