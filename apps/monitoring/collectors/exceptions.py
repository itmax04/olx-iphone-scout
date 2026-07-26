"""Collector error hierarchy mapped to safe error codes."""

from apps.core.enums import ErrorCode


class CollectorError(Exception):
    error_code: str = ErrorCode.INTERNAL_ERROR
    safe_message: str = "Ошибка сбора данных."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.safe_message)


class LayoutChangedError(CollectorError):
    error_code = ErrorCode.OLX_LAYOUT_CHANGED
    safe_message = "Ожидаемый контейнер объявлений не найден. Верстка OLX могла измениться."


class CaptchaError(CollectorError):
    error_code = ErrorCode.OLX_CAPTCHA
    safe_message = "OLX показал CAPTCHA. Мониторинг остановлен, обход запрещен."


class BlockedError(CollectorError):
    error_code = ErrorCode.OLX_BLOCKED
    safe_message = "OLX вернул 403. Доступ временно ограничен."


class OlxRateLimitedError(CollectorError):
    error_code = ErrorCode.OLX_RATE_LIMITED
    safe_message = "OLX вернул 429. Частота запросов слишком высокая."


class NavigationTimeoutError(CollectorError):
    error_code = ErrorCode.OLX_TIMEOUT
    safe_message = "Страница OLX не загрузилась за отведенное время."


class DisallowedNavigationError(CollectorError):
    error_code = ErrorCode.CONFIGURATION_ERROR
    safe_message = "Переход на неразрешенный адрес заблокирован."
