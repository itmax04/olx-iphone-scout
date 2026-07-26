"""S-11 / U-38: секреты в логах заменяются на [REDACTED]."""

import logging

from apps.core.logging import JsonFormatter, RedactionFilter, redact_mapping, redact_text


def test_redact_key_value_pairs():
    text = "password=hunter2 token: abc123 api_key=xyz cookie=SESSION"
    redacted = redact_text(text)
    assert "hunter2" not in redacted
    assert "abc123" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_database_url():
    redacted = redact_text("postgresql://user:secretpw@db:5432/app")
    assert "secretpw" not in redacted


def test_redact_telegram_token_in_url():
    redacted = redact_text("POST https://api.telegram.org/bot123456:AAAbbbCCC/sendMessage")
    assert "AAAbbbCCC" not in redacted
    assert "/bot[REDACTED]" in redacted


def test_redact_openai_key():
    redacted = redact_text("using key sk-abcdefghijklmnop1234567890")
    assert "sk-abcdefghijklmnop" not in redacted


def test_redact_mapping():
    data = redact_mapping({"password": "x", "nested": {"api_key": "y"}, "safe": "ok"})
    assert data["password"] == "[REDACTED]"
    assert data["nested"]["api_key"] == "[REDACTED]"
    assert data["safe"] == "ok"


def test_filter_and_formatter_pipeline():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=1,
        msg="login with password=qwerty",
        args=(),
        exc_info=None,
    )
    RedactionFilter().filter(record)
    output = JsonFormatter().format(record)
    assert "qwerty" not in output
