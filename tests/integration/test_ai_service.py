"""I-22..I-25, I-33, U-41: AI-сервис с fake-клиентом; ноль реальных вызовов."""

import json
from decimal import Decimal

import pytest

from apps.analysis.client import AiProviderError, AiRawResponse
from apps.analysis.enums import AiStatus, AiTier
from apps.analysis.models import AiAnalysis
from apps.analysis.services import (
    analyze_listing,
    estimate_cost_usd,
    process_pending_analyses,
    request_reanalysis,
)
from tests.unit.test_ai_schema import VALID

pytestmark = pytest.mark.django_db


class FakeClient:
    def __init__(self, responses=None, error=None):
        self.calls = []
        self.error = error
        self.responses = responses or [json.dumps(VALID)]
        self._index = 0

    def generate(self, *, model, system, user, schema):
        self.calls.append({"model": model, "system": system, "user": user})
        if self.error is not None:
            raise self.error
        text = self.responses[min(self._index, len(self.responses) - 1)]
        self._index += 1
        return AiRawResponse(text=text, model_id=model, input_tokens=1000, output_tokens=500)


@pytest.fixture
def ai_on(settings, db):
    settings.AI_ENABLED = True
    settings.OPENAI_API_KEY = "sk-test-not-real"
    from apps.core.models import AppState

    state = AppState.get_solo()
    state.ai_enabled = True
    state.save()
    return settings


class TestSuccess:
    def test_valid_response_saved(self, listing, ai_on):
        client = FakeClient()
        analysis = analyze_listing(listing, client=client)
        assert analysis is not None
        assert analysis.status == AiStatus.SUCCESS  # I-22
        assert analysis.input_tokens == 1000
        assert analysis.output_tokens == 500
        assert analysis.estimated_cost_usd == estimate_cost_usd(AiTier.FAST, 1000, 500)
        listing.refresh_from_db()
        assert listing.analysis_status == "SUCCESS"
        assert listing.current_risk_level == "MEDIUM"

    def test_cache_reused(self, listing, ai_on):
        client = FakeClient()
        analyze_listing(listing, client=client)
        calls_after_first = len(client.calls)
        second = analyze_listing(listing, client=client)
        assert len(client.calls) == calls_after_first  # I-25: без второго вызова
        assert second.status == AiStatus.SUCCESS

    def test_low_confidence_escalates_to_deep(self, listing, ai_on):
        low_confidence = dict(VALID, confidence=0.4)
        client = FakeClient(responses=[json.dumps(low_confidence), json.dumps(VALID)])
        final = analyze_listing(listing, client=client)
        assert final.tier == AiTier.DEEP
        models = [call["model"] for call in client.calls]
        assert models[0] != models[1]  # fast, затем deep


class TestFailures:
    def test_invalid_json_one_retry_then_fail(self, listing, ai_on):
        client = FakeClient(responses=["не json", "все еще не json"])
        result = analyze_listing(listing, client=client)
        # fast невалиден дважды -> schema failure -> эскалация в deep,
        # deep тоже вернет мусор -> итог None
        listing.refresh_from_db()
        assert listing.analysis_status == "FAILED"  # I-23
        fast_rows = AiAnalysis.objects.filter(tier=AiTier.FAST)
        assert fast_rows.filter(status=AiStatus.FAILED).exists()
        assert result is None

    def test_provider_error_graceful(self, listing, ai_on):
        client = FakeClient(error=AiProviderError("OpenAI 429"))
        result = analyze_listing(listing, client=client)
        assert result is None  # I-24: приложение живо, deterministic остается
        listing.refresh_from_db()
        assert listing.analysis_status == "FAILED"

    def test_budget_exceeded_blocks_call(self, listing, ai_on, settings):
        """U-41: превышение дневного лимита не вызывает provider."""
        settings.AI_DAILY_HARD_LIMIT_USD = Decimal("0.000001")
        AiAnalysis.objects.create(
            listing=listing,
            content_hash=listing.content_hash,
            tier=AiTier.FAST,
            requested_model_id="x",
            prompt_version="v",
            schema_version=1,
            revision=99,
            attempt=1,
            status=AiStatus.SUCCESS,
            estimated_cost_usd=Decimal("1.00"),
        )
        client = FakeClient()
        result = analyze_listing(listing, client=client)
        assert result is None
        assert client.calls == []  # provider не вызван
        from apps.alerts.models import NotificationOutbox

        assert NotificationOutbox.objects.filter(event_type="SYSTEM_ERROR").exists()


class TestReanalyzeQueue:
    def test_cache_hit_no_queue(self, listing, ai_on):
        analyze_listing(listing, client=FakeClient())
        result = request_reanalysis(listing)
        assert result["cache_hit"] is True
        assert result["queued"] is False

    def test_force_requires_reason(self, listing, ai_on):
        analyze_listing(listing, client=FakeClient())
        with pytest.raises(ValueError):
            request_reanalysis(listing, force=True, force_reason="X")

    def test_force_creates_new_revision(self, listing, ai_on):
        analyze_listing(listing, client=FakeClient())
        result = request_reanalysis(listing, force=True, force_reason="Продавец обновил описание")
        assert result["queued"] is True
        assert result["revision"] >= 1  # I-33
        pending = AiAnalysis.objects.get(pk=result["analysis_id"])
        assert pending.status == AiStatus.PENDING
        assert pending.force_reason == "Продавец обновил описание"

        # worker подхватывает очередь
        done = process_pending_analyses(client=FakeClient())
        assert done == 1
        pending.refresh_from_db()
        assert pending.status == AiStatus.SUCCESS

    def test_pending_marked_failed_when_ai_off(self, listing, ai_on, settings):
        result = request_reanalysis(listing)
        assert result["queued"] is True
        settings.AI_ENABLED = False
        done = process_pending_analyses(client=FakeClient())
        assert done == 0
        analysis = AiAnalysis.objects.get(pk=result["analysis_id"])
        assert analysis.status == AiStatus.FAILED
