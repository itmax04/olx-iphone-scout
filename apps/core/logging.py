"""Safe logging: redaction filter plus text/JSON formatters."""

import json
import logging
import re
from datetime import UTC, datetime

from apps.core.middleware import get_current_request_id

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)\b(password|secret|token|authorization|cookie|session|api_key|database_url)\b"
    r"(\s*[=:]\s*)([^\s,;&\"']+)"
)
_URL_CREDENTIALS_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
_TELEGRAM_TOKEN_PATTERN = re.compile(r"/bot\d+:[A-Za-z0-9_-]+")
_OPENAI_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")

_EXTRA_FIELDS = (
    "event",
    "listing_id",
    "search_profile_id",
    "scan_run_id",
    "outbox_id",
    "duration_ms",
    "error_code",
    "correlation_id",
)


def redact_text(text: str) -> str:
    text = _SENSITIVE_KEY_PATTERN.sub(r"\1\2[REDACTED]", text)
    text = _URL_CREDENTIALS_PATTERN.sub(r"\1[REDACTED]@", text)
    text = _TELEGRAM_TOKEN_PATTERN.sub("/bot[REDACTED]", text)
    text = _OPENAI_KEY_PATTERN.sub("[REDACTED]", text)
    return text


def redact_mapping(data: dict[str, object]) -> dict[str, object]:
    """Replace values of sensitive keys in a flat mapping."""
    cleaned: dict[str, object] = {}
    for key, value in data.items():
        if re.search(
            r"(?i)\b(password|secret|token|authorization|cookie|session|api_key|database_url)\b",
            str(key),
        ):
            cleaned[key] = "[REDACTED]"
        elif isinstance(value, str):
            cleaned[key] = redact_text(value)
        elif isinstance(value, dict):
            cleaned[key] = redact_mapping(value)  # type: ignore[arg-type]
        else:
            cleaned[key] = value
    return cleaned


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = ()
        return True


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"{timestamp} {record.levelname} {record.name}: {record.getMessage()}"]
        request_id = get_current_request_id()
        if request_id:
            parts.append(f"request_id={request_id}")
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                parts.append(f"{field}={value}")
        if record.exc_info:
            parts.append(self.formatException(record.exc_info).replace("\n", " | "))
        return redact_text(" ".join(parts))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_current_request_id()
        if request_id:
            payload["request_id"] = request_id
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact_text(json.dumps(payload, ensure_ascii=False, default=str))
