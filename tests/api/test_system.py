"""A-21..A-24, A-31..A-33: system/settings/integrations API."""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.models import AppState

pytestmark = pytest.mark.django_db


def post_json(client, path, body=None):
    return client.post(path, data=json.dumps(body or {}), content_type="application/json")


class TestPauseResume:
    def test_pause_persists(self, admin_client_ru):
        response = post_json(admin_client_ru, "/api/v1/system/pause/", {"reason": "проверка"})
        assert response.status_code == 200
        assert AppState.get_solo().monitoring_paused is True  # A-23

    def test_pause_idempotent(self, admin_client_ru):
        post_json(admin_client_ru, "/api/v1/system/pause/", {"reason": "x"})
        assert (
            post_json(admin_client_ru, "/api/v1/system/pause/", {"reason": "x"}).status_code == 200
        )

    def test_resume_ok(self, admin_client_ru):
        post_json(admin_client_ru, "/api/v1/system/pause/", {"reason": "x"})
        response = post_json(admin_client_ru, "/api/v1/system/resume/")
        assert response.status_code == 200
        assert AppState.get_solo().monitoring_paused is False

    def test_resume_during_cooldown_409(self, admin_client_ru):
        state = AppState.get_solo()
        state.monitoring_paused = True
        state.safety_block_until = timezone.now() + timedelta(minutes=10)
        state.safety_ack_required = True
        state.save()
        assert post_json(admin_client_ru, "/api/v1/system/resume/").status_code == 409  # A-24

    def test_resume_after_cooldown_needs_ack(self, admin_client_ru):
        state = AppState.get_solo()
        state.monitoring_paused = True
        state.safety_block_until = timezone.now() - timedelta(minutes=1)
        state.safety_ack_required = True
        state.save()
        assert post_json(admin_client_ru, "/api/v1/system/resume/").status_code == 409
        response = post_json(admin_client_ru, "/api/v1/system/resume/", {"acknowledge_risk": True})
        assert response.status_code == 200

    def test_reason_too_long_400(self, admin_client_ru):
        response = post_json(admin_client_ru, "/api/v1/system/pause/", {"reason": "x" * 300})
        assert response.status_code == 400


class TestIntegrations:
    def test_telegram_not_configured_422(self, admin_client_ru):
        response = post_json(admin_client_ru, "/api/v1/integrations/telegram/test/")
        assert response.status_code == 422  # A-21

    def test_openai_check_not_configured_422(self, admin_client_ru):
        response = post_json(admin_client_ru, "/api/v1/integrations/openai/check/")
        assert response.status_code == 422  # A-32

    def test_openai_check_configured(self, admin_client_ru, settings):
        settings.OPENAI_API_KEY = "sk-test-not-real"
        response = post_json(admin_client_ru, "/api/v1/integrations/openai/check/")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["configured"] is True
        assert data["provider_called"] is False


class TestSettings:
    def test_get_settings_no_secrets(self, admin_client_ru, settings):
        settings.OPENAI_API_KEY = "sk-super-secret-value"
        response = admin_client_ru.get("/api/v1/settings/")
        assert response.status_code == 200
        text = response.content.decode()
        assert "sk-super-secret-value" not in text
        assert response.json()["data"]["openai_configured"] is True

    def test_patch_bounds(self, admin_client_ru):
        response = admin_client_ru.patch(
            "/api/v1/settings/",
            data=json.dumps({"market_price_stale_days": 99}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_patch_ok(self, admin_client_ru):
        response = admin_client_ru.patch(
            "/api/v1/settings/",
            data=json.dumps({"market_price_stale_days": 10, "ai_escalation_confidence": "0.800"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        state = AppState.get_solo()
        assert state.market_price_stale_days == 10
        assert str(state.ai_escalation_confidence) == "0.800"

    def test_patch_secret_fields_rejected(self, admin_client_ru):
        response = admin_client_ru.patch(
            "/api/v1/settings/",
            data=json.dumps({"openai_api_key": "sk-x"}),
            content_type="application/json",
        )
        assert response.status_code == 400


class TestDiagnostics:
    def test_system_status_safe(self, admin_client_ru, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:secret-token-value"
        response = admin_client_ru.get("/api/v1/system/status/")
        assert response.status_code == 200
        text = response.content.decode()
        assert "secret-token-value" not in text  # A-31
        assert response.json()["data"]["telegram_configured"] is False  # chat_id пуст

    def test_diagnostic_attachment(self, admin_client_ru):
        response = admin_client_ru.get("/api/v1/system/diagnostic/")
        assert response.status_code == 200
        assert "attachment" in response["Content-Disposition"]

    def test_scan_run_diagnostic_safe_fields(self, admin_client_ru):
        from apps.monitoring.models import ScanRun

        run = ScanRun.objects.create(status="FAILED", error_code="OLX_LAYOUT_CHANGED")
        response = admin_client_ru.get(f"/api/v1/scan-runs/{run.pk}/diagnostic/")
        assert response.status_code == 200
        data = json.loads(response.content)["data"]
        assert set(data.keys()) <= {
            "id",
            "search_profile",
            "correlation_id",
            "status",
            "started_at",
            "finished_at",
            "duration_ms",
            "found_count",
            "new_count",
            "changed_count",
            "candidate_count",
            "retry_count",
            "error_code",
            "error_message",
            "parser_version",
        }

    def test_cleanup_preview_read_only(self, admin_client_ru):
        from apps.monitoring.models import ScanRun

        ScanRun.objects.create(status="SUCCESS")
        response = post_json(admin_client_ru, "/api/v1/system/cleanup/preview/")
        assert response.status_code == 200
        assert "would_delete" in response.json()["data"]
        assert ScanRun.objects.count() == 1  # A-33: ничего не удалено
