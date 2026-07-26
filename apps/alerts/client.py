"""Telegram Bot API client (outbound sendMessage only). Token never logged."""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    def __init__(
        self,
        message: str,
        *,
        permanent: bool = False,
        retry_after: int | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.permanent = permanent
        self.retry_after = retry_after
        self.status_code = status_code


class TelegramNotConfigured(TelegramError):
    def __init__(self) -> None:
        super().__init__("Telegram не настроен (нет token или chat ID).", permanent=True)


class TelegramClient:
    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.timeout = settings.TELEGRAM_TIMEOUT_SECONDS
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self._transport)

    def send_message(self, text: str, *, url_button: tuple[str, str] | None = None) -> str:
        """Send a message to the configured chat. Returns telegram message id."""
        if not self.configured:
            raise TelegramNotConfigured()
        payload: dict = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if url_button is not None:
            label, target = url_button
            if target.startswith("https://"):
                payload["reply_markup"] = {
                    "inline_keyboard": [[{"text": label, "url": target}]]
                }
        try:
            with self._client() as client:
                response = client.post(
                    f"{API_BASE}/bot{self.token}/sendMessage", json=payload
                )
        except httpx.HTTPError as exc:
            raise TelegramError(f"Сетевая ошибка Telegram: {type(exc).__name__}")

        if response.status_code == 429:
            retry_after = 30
            try:
                retry_after = int(
                    response.json().get("parameters", {}).get("retry_after", 30)
                )
            except Exception:  # pragma: no cover - malformed body
                pass
            raise TelegramError("Telegram 429", retry_after=retry_after, status_code=429)
        if 400 <= response.status_code < 500:
            raise TelegramError(
                f"Telegram отклонил запрос ({response.status_code}).",
                permanent=True,
                status_code=response.status_code,
            )
        if response.status_code >= 500:
            raise TelegramError(
                f"Telegram временно недоступен ({response.status_code}).",
                status_code=response.status_code,
            )
        try:
            data = response.json()
            return str(data["result"]["message_id"])
        except Exception:
            raise TelegramError("Неожиданный ответ Telegram.")

    def get_updates(self) -> list[dict]:
        """Used only by discover_telegram_chat_id."""
        if not self.token:
            raise TelegramNotConfigured()
        with self._client() as client:
            response = client.get(f"{API_BASE}/bot{self.token}/getUpdates")
        response.raise_for_status()
        return list(response.json().get("result", []))

    def get_webhook_info(self) -> dict:
        if not self.token:
            raise TelegramNotConfigured()
        with self._client() as client:
            response = client.get(f"{API_BASE}/bot{self.token}/getWebhookInfo")
        response.raise_for_status()
        return dict(response.json().get("result", {}))


def get_client(**kwargs) -> TelegramClient:
    return TelegramClient(**kwargs)
