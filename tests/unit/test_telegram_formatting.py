"""U-32..U-35: экранирование, усечение, fingerprints."""

from decimal import Decimal

import pytest

from apps.alerts.formatting import (
    escape_html,
    format_candidate_message,
    format_money,
    render_message,
    truncate,
)

pytestmark = pytest.mark.django_db


class TestEscaping:
    def test_html_escaped(self):
        text = escape_html('<script>alert("x")</script> & <b>')
        assert "<script>" not in text
        assert "&lt;script&gt;" in text
        assert "&amp;" in text

    def test_candidate_message_escapes_title(self):
        message = format_candidate_message({"title": "<b>iPhone</b> 13"})
        assert "<b>" not in message
        assert "&lt;b&gt;" in message


class TestTruncation:
    def test_long_text_truncated_deterministically(self):
        long_text = "щ" * 10000
        first = truncate(long_text)
        second = truncate(long_text)
        assert first == second
        assert len(first) <= 4096
        assert first.endswith("…")

    def test_short_text_untouched(self):
        assert truncate("привет") == "привет"


class TestMoney:
    def test_format_money(self):
        assert format_money(Decimal("14800.00")) == "14 800 грн"
        assert format_money(None) == "—"


class TestFingerprints:
    def test_same_event_same_fingerprint(self, listing):
        from apps.alerts.services import enqueue_candidate_alert

        first = enqueue_candidate_alert(listing)
        duplicate = enqueue_candidate_alert(listing)
        assert first is not None
        assert duplicate is None  # U-34: одинаковая причина -> один outbox

    def test_different_event_types_different_fingerprints(self, listing):
        from apps.alerts.services import enqueue_candidate_alert, enqueue_price_drop_alert

        candidate = enqueue_candidate_alert(listing)
        drop = enqueue_price_drop_alert(listing, old_price=Decimal("15000.00"))
        assert candidate is not None and drop is not None  # U-35
        assert candidate.fingerprint != drop.fingerprint

    def test_price_drop_fingerprint_includes_new_price(self, listing):
        """F-18: новая цена входит в fingerprint."""
        from apps.alerts.services import enqueue_price_drop_alert

        first = enqueue_price_drop_alert(listing, old_price=Decimal("15000.00"))
        listing.current_price_uah = Decimal("9999.00")
        listing.save(update_fields=["current_price_uah"])
        second = enqueue_price_drop_alert(listing, old_price=Decimal("11500.00"))
        assert first is not None and second is not None
        assert first.fingerprint != second.fingerprint

    def test_system_incident_hour_rate_limit(self, db):
        from apps.alerts.services import enqueue_system_incident

        first = enqueue_system_incident("OLX_CAPTCHA", "captcha")
        repeat = enqueue_system_incident("OLX_CAPTCHA", "captcha again")
        assert first is not None
        assert repeat is None  # не чаще раза в час


class TestRenderMessage:
    def test_system_message(self):
        text = render_message("SYSTEM_ERROR", {"error_code": "OLX_BLOCKED", "message": "403"})
        assert "OLX_BLOCKED" in text

    def test_candidate_message_full(self):
        payload = {
            "title": "iPhone 13 128GB",
            "price": "11 500 грн",
            "sale_price": "14 800 грн",
            "reserve": "900 грн",
            "profit": "2 400 грн",
            "risk_level": "MEDIUM",
            "ai_confidence": "82%",
            "facts": ["АКБ: продавец указал 87%"],
            "missing_checks": ["Face ID и True Tone"],
            "seller_questions": ["Вітаю! Чи працюють Face ID та True Tone?"],
        }
        text = format_candidate_message(payload)
        assert "iPhone 13 128GB" in text
        assert "2 400 грн" in text
        assert "Вітаю!" in text
        assert "82%" in text
