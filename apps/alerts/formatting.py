"""Safe Telegram message formatting: HTML parse mode, escaping, truncation."""

from decimal import Decimal

TELEGRAM_MAX_LEN = 4096
_RISK_LABELS = {
    "LOW": "низкий",
    "MEDIUM": "средний",
    "HIGH": "высокий",
    "UNKNOWN": "не определен",
}


def escape_html(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    whole = int(value)
    return f"{whole:,}".replace(",", " ") + " грн"


def truncate(text: str, limit: int = TELEGRAM_MAX_LEN) -> str:
    """Deterministic truncation that keeps the message valid."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def format_candidate_message(payload: dict) -> str:
    """Build the candidate alert text from a prevalidated safe payload."""
    lines = [
        f"🔥 Новый кандидат: {escape_html(payload.get('title', ''))}",
        "",
        f"Цена продавца: {escape_html(payload.get('price', '—'))}",
        f"Ожидаемая быстрая продажа: {escape_html(payload.get('sale_price', '—'))}",
        f"Резерв дефектов и расходов: {escape_html(payload.get('reserve', '—'))}",
        f"Ожидаемая прибыль: {escape_html(payload.get('profit', '—'))}",
        "",
    ]
    risk = payload.get("risk_level", "UNKNOWN")
    confidence = payload.get("ai_confidence")
    risk_line = f"Риск: {_RISK_LABELS.get(risk, 'не определен')}"
    if confidence:
        risk_line += f" · уверенность AI: {escape_html(str(confidence))}"
    else:
        risk_line += " · AI недоступен"
    lines.append(risk_line)

    for fact in payload.get("facts", [])[:6]:
        lines.append(escape_html(fact))

    checks = payload.get("missing_checks", [])
    if checks:
        lines.append("")
        lines.append("Что проверить:")
        for check in checks[:6]:
            lines.append(f"• {escape_html(check)}")

    questions = payload.get("seller_questions", [])
    if questions:
        lines.append("")
        lines.append("Сообщение продавцу:")
        lines.append(f"«{escape_html(questions[0][:300])}»")

    return truncate("\n".join(lines))


def format_price_drop_message(payload: dict) -> str:
    lines = [
        f"📉 Цена снижена: {escape_html(payload.get('title', ''))}",
        "",
        f"Старая цена: {escape_html(payload.get('old_price', '—'))}",
        f"Новая цена: {escape_html(payload.get('price', '—'))}",
        f"Ожидаемая прибыль: {escape_html(payload.get('profit', '—'))}",
    ]
    return truncate("\n".join(lines))


def format_system_message(payload: dict) -> str:
    lines = [
        f"⚠️ Системное событие: {escape_html(payload.get('error_code', ''))}",
        escape_html(payload.get("message", "")),
    ]
    return truncate("\n".join(lines))


def format_recovered_message(payload: dict) -> str:
    lines = [
        f"✅ Восстановлено: {escape_html(payload.get('error_code', ''))}",
        escape_html(payload.get("message", "")),
    ]
    return truncate("\n".join(lines))


def format_test_message(payload: dict) -> str:
    return truncate(
        "Тест OLX iPhone Scout\n"
        f"Время: {escape_html(payload.get('timestamp', ''))}\n"
        f"Окружение: {escape_html(payload.get('environment', ''))}"
    )


FORMATTERS = {
    "NEW_CANDIDATE": format_candidate_message,
    "PRICE_DROP": format_price_drop_message,
    "CONTENT_CHANGED": format_price_drop_message,
    "CAPTCHA": format_system_message,
    "SYSTEM_ERROR": format_system_message,
    "RECOVERED": format_recovered_message,
    "TEST": format_test_message,
}


def render_message(event_type: str, payload: dict) -> str:
    formatter = FORMATTERS.get(event_type, format_system_message)
    return formatter(payload)
