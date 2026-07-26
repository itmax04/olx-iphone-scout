"""Send one test Telegram message through the outbox path."""

from django.core.management.base import BaseCommand, CommandError

from apps.alerts.client import get_client
from apps.alerts.formatting import render_message
from apps.alerts.services import enqueue_test_message


class Command(BaseCommand):
    help = "Queue and immediately send a test Telegram message."

    def handle(self, *args: object, **options: object) -> None:
        client = get_client()
        if not client.configured:
            raise CommandError(
                "Telegram не настроен: заполните TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID."
            )
        item = enqueue_test_message()
        if item is None:
            raise CommandError("Не удалось создать запись outbox (дубликат).")
        text = render_message(item.event_type, item.payload)
        try:
            message_id = client.send_message(text)
        except Exception as exc:
            raise CommandError(f"Отправка не удалась: {exc}")
        from django.utils import timezone

        from apps.alerts.enums import OutboxStatus

        item.status = OutboxStatus.SENT
        item.telegram_message_id = message_id
        item.sent_at = timezone.now()
        item.save(update_fields=["status", "telegram_message_id", "sent_at", "updated_at"])
        self.stdout.write(self.style.SUCCESS("Тестовое сообщение отправлено."))
