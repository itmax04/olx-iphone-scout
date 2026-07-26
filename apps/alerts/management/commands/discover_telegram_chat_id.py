"""Print candidate chat IDs from getUpdates. Never prints the token or texts."""

from django.core.management.base import BaseCommand, CommandError

from apps.alerts.client import TelegramError, get_client


class Command(BaseCommand):
    help = (
        "Discover your Telegram chat ID. Send /start to the bot first, then run this. "
        "The token is read only from the environment."
    )

    def handle(self, *args: object, **options: object) -> None:
        client = get_client()
        if not client.token:
            raise CommandError("TELEGRAM_BOT_TOKEN не задан в окружении (.env).")

        try:
            webhook = client.get_webhook_info()
        except (TelegramError, Exception) as exc:
            raise CommandError(f"Не удалось обратиться к Telegram: {type(exc).__name__}")

        if webhook.get("url"):
            raise CommandError(
                "У бота настроен webhook, getUpdates недоступен. Удалите webhook "
                "вручную (эта команда его не трогает) и повторите."
            )

        try:
            updates = client.get_updates()
        except Exception as exc:
            raise CommandError(f"Ошибка getUpdates: {type(exc).__name__}")

        chats: dict[str, str] = {}
        for update in updates:
            message = update.get("message") or update.get("edited_message") or {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            username = chat.get("username") or chat.get("first_name") or ""
            chats[str(chat_id)] = username

        if not chats:
            self.stdout.write(
                "No chats found. Отправьте боту /start, подождите 5 секунд и повторите."
            )
            return

        for chat_id, username in chats.items():
            suffix = f"  (@{username})" if username else ""
            self.stdout.write(f"TELEGRAM_CHAT_ID={chat_id}{suffix}")
