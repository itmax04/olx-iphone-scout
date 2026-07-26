"""AI analysis orchestration: cache, budgets, fast/deep routing, fallbacks.

The provider is only called when effective_ai() is true AND the hard budget
allows it. Tests always inject a fake client; CI never pays.
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.analysis.client import AiProviderError, AiRawResponse
from apps.analysis.enums import AiStatus, AiTier
from apps.analysis.models import AiAnalysis
from apps.analysis.prompts import SYSTEM_PROMPT, build_user_content, prompt_version
from apps.analysis.routing import should_escalate
from apps.analysis.schemas import AiResultV1, json_schema_for_provider, validate_ai_result
from apps.monitoring.enums import AnalysisState, RiskLevel
from apps.monitoring.models import Listing

logger = logging.getLogger(__name__)

_RISK_MAP = {"low": RiskLevel.LOW, "medium": RiskLevel.MEDIUM, "high": RiskLevel.HIGH}


class AiBudgetExceeded(Exception):
    pass


class AiAlreadyRunning(Exception):
    pass


# ---------- Cost / budget ----------


def estimate_cost_usd(tier: str, input_tokens: int, output_tokens: int) -> Decimal:
    if tier == AiTier.DEEP:
        rate_in = settings.OPENAI_DEEP_INPUT_USD_PER_MILLION
        rate_out = settings.OPENAI_DEEP_OUTPUT_USD_PER_MILLION
    else:
        rate_in = settings.OPENAI_FAST_INPUT_USD_PER_MILLION
        rate_out = settings.OPENAI_FAST_OUTPUT_USD_PER_MILLION
    million = Decimal("1000000")
    cost = (Decimal(input_tokens) / million) * rate_in + (
        Decimal(output_tokens) / million
    ) * rate_out
    return cost.quantize(Decimal("0.000001"))


def spent_usd_since(since) -> Decimal:
    total = AiAnalysis.objects.filter(created_at__gte=since).aggregate(
        total=Sum("estimated_cost_usd")
    )["total"]
    return total or Decimal("0")


def check_budget() -> None:
    """Raise AiBudgetExceeded when a hard limit is already reached."""
    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    if spent_usd_since(day_start) >= settings.AI_DAILY_HARD_LIMIT_USD:
        raise AiBudgetExceeded("Дневной лимит расходов AI исчерпан.")
    if spent_usd_since(month_start) >= settings.AI_MONTHLY_HARD_LIMIT_USD:
        raise AiBudgetExceeded("Месячный лимит расходов AI исчерпан.")


# ---------- Cache helpers ----------


def _cache_key_filter(listing: Listing, tier: str, revision: int) -> dict:
    model = settings.OPENAI_DEEP_MODEL if tier == AiTier.DEEP else settings.OPENAI_FAST_MODEL
    return {
        "listing": listing,
        "content_hash": listing.content_hash,
        "tier": tier,
        "schema_version": settings.AI_SCHEMA_VERSION,
        "prompt_version": prompt_version(),
        "requested_model_id": model,
        "revision": revision,
    }


def find_cached_success(listing: Listing, tier: str, revision: int = 0) -> AiAnalysis | None:
    return AiAnalysis.objects.filter(
        **_cache_key_filter(listing, tier, revision), status=AiStatus.SUCCESS
    ).first()


def next_revision(listing: Listing, tier: str) -> int:
    last = (
        AiAnalysis.objects.filter(
            listing=listing,
            content_hash=listing.content_hash,
            tier=tier,
            schema_version=settings.AI_SCHEMA_VERSION,
            prompt_version=prompt_version(),
        )
        .order_by("-revision")
        .first()
    )
    return (last.revision + 1) if last else 0


# ---------- Single-tier execution ----------


def _deterministic_facts(listing: Listing) -> dict:
    from apps.pricing.services import extract_listing_facts

    facts = extract_listing_facts(listing.title, listing.description)
    return {
        "model_key": facts.model_key,
        "storage_gb": facts.storage_gb,
        "detected_defects": list(facts.defect_codes),
        "battery_percent": facts.battery_percent,
        "price_uah": str(listing.current_price_uah) if listing.current_price_uah else None,
        "seller_type": listing.seller_type,
    }


def create_analysis_row(
    listing: Listing,
    tier: str,
    *,
    revision: int,
    force_reason: str = "",
    status: str = AiStatus.PENDING,
) -> AiAnalysis:
    """Create the next attempt row for a cache key."""
    cache_filter = _cache_key_filter(listing, tier, revision)
    last_attempt = AiAnalysis.objects.filter(**cache_filter).order_by("-attempt").first()
    attempt = (last_attempt.attempt + 1) if last_attempt else 1
    if attempt > 5:
        raise AiProviderError("Достигнут предел попыток анализа.", code="AI_INVALID_OUTPUT")
    return AiAnalysis.objects.create(
        **cache_filter,
        attempt=attempt,
        force_reason=force_reason,
        status=status,
        started_at=timezone.now() if status == AiStatus.RUNNING else None,
    )


def _run_tier(
    listing: Listing, tier: str, client, *, revision: int, force_reason: str = ""
) -> AiAnalysis:
    """One provider round for a tier; one extra retry on invalid JSON."""
    cache_filter = _cache_key_filter(listing, tier, revision)
    cached = AiAnalysis.objects.filter(**cache_filter, status=AiStatus.SUCCESS).first()
    if cached is not None:
        return cached

    check_budget()
    analysis = create_analysis_row(
        listing, tier, revision=revision, force_reason=force_reason, status=AiStatus.RUNNING
    )
    return execute_analysis(analysis, client)


def execute_analysis(analysis: AiAnalysis, client) -> AiAnalysis:
    """Run the provider for one existing AiAnalysis row (PENDING or RUNNING)."""
    listing = analysis.listing
    if analysis.status == AiStatus.PENDING:
        analysis.status = AiStatus.RUNNING
        analysis.started_at = timezone.now()
        analysis.save(update_fields=["status", "started_at"])

    user_content = build_user_content(
        title=listing.title,
        description=listing.description or "",
        deterministic_facts=_deterministic_facts(listing),
    )

    tier = analysis.tier
    invalid_retry_done = False
    while True:
        try:
            raw: AiRawResponse = client.generate(
                model=analysis.requested_model_id,
                system=SYSTEM_PROMPT,
                user=user_content,
                schema=json_schema_for_provider(),
            )
        except AiProviderError as exc:
            _mark_failed(analysis, exc.code, str(exc))
            raise

        cost = estimate_cost_usd(tier, raw.input_tokens, raw.output_tokens)
        try:
            import json as _json

            result: AiResultV1 = validate_ai_result(_json.loads(raw.text))
        except Exception:
            if not invalid_retry_done:
                invalid_retry_done = True
                analysis.input_tokens = (analysis.input_tokens or 0) + raw.input_tokens
                analysis.output_tokens = (analysis.output_tokens or 0) + raw.output_tokens
                analysis.estimated_cost_usd = (analysis.estimated_cost_usd or Decimal("0")) + cost
                analysis.save(update_fields=["input_tokens", "output_tokens", "estimated_cost_usd"])
                continue
            _mark_failed(
                analysis,
                "AI_INVALID_OUTPUT",
                "Модель вернула невалидный JSON дважды.",
                extra_cost=cost,
                tokens=(raw.input_tokens, raw.output_tokens),
            )
            raise AiProviderError("Невалидный вывод модели.", code="AI_INVALID_OUTPUT")

        analysis.status = AiStatus.SUCCESS
        analysis.model_id = raw.model_id
        analysis.result = result.model_dump()
        analysis.confidence = Decimal(str(result.confidence)).quantize(Decimal("0.001"))
        analysis.risk_level = _RISK_MAP.get(result.risk_level, RiskLevel.UNKNOWN)
        analysis.input_tokens = (analysis.input_tokens or 0) + raw.input_tokens
        analysis.output_tokens = (analysis.output_tokens or 0) + raw.output_tokens
        analysis.estimated_cost_usd = (analysis.estimated_cost_usd or Decimal("0")) + cost
        analysis.completed_at = timezone.now()
        analysis.error_code = ""
        analysis.error_message = ""
        analysis.save()
        return analysis


def _mark_failed(
    analysis: AiAnalysis,
    code: str,
    message: str,
    *,
    extra_cost: Decimal | None = None,
    tokens: tuple[int, int] | None = None,
) -> None:
    analysis.status = AiStatus.FAILED
    analysis.error_code = code[:64]
    analysis.error_message = message[:500]
    analysis.completed_at = timezone.now()
    if tokens:
        analysis.input_tokens = (analysis.input_tokens or 0) + tokens[0]
        analysis.output_tokens = (analysis.output_tokens or 0) + tokens[1]
    if extra_cost:
        analysis.estimated_cost_usd = (analysis.estimated_cost_usd or Decimal("0")) + extra_cost
    analysis.save()


# ---------- Public orchestration ----------


def analyze_listing(
    listing: Listing,
    *,
    client=None,
    force: bool = False,
    force_reason: str = "",
) -> AiAnalysis | None:
    """Run fast (and maybe deep) analysis. Returns the final analysis or None.

    Never raises on provider trouble: deterministic evaluation must survive.
    Raises AiAlreadyRunning for concurrent manual requests.
    """
    from apps.analysis.selectors import running_analysis_exists
    from apps.core.services import effective_ai, get_app_state

    if not effective_ai():
        return None
    if running_analysis_exists(listing):
        raise AiAlreadyRunning("Анализ уже выполняется.")

    revision = 0
    if force:
        if not force_reason or not (5 <= len(force_reason) <= 255):
            raise ValueError("Для повторного анализа нужна причина 5–255 символов.")
        revision = next_revision(listing, AiTier.FAST)
        if revision == 0 and find_cached_success(listing, AiTier.FAST, 0):
            revision = 1

    if not force:
        cached = find_cached_success(listing, AiTier.FAST, 0)
        if cached is not None:
            deep_cached = find_cached_success(listing, AiTier.DEEP, 0)
            cached_final = deep_cached or cached
            _apply_to_listing(listing, cached_final)
            return cached_final

    if client is None:
        from apps.analysis.client import get_ai_client

        try:
            client = get_ai_client()
        except AiProviderError as exc:
            logger.warning("ai_client_unavailable %s", exc)
            _set_listing_state(listing, AnalysisState.FAILED)
            return None

    state = get_app_state()
    Listing.objects.filter(pk=listing.pk).update(analysis_status=AnalysisState.RUNNING)

    fast_result: AiResultV1 | None = None
    fast_analysis: AiAnalysis | None = None
    final: AiAnalysis | None = None
    fast_schema_failed = False
    try:
        fast_analysis = _run_tier(
            listing, AiTier.FAST, client, revision=revision, force_reason=force_reason
        )
        fast_result = validate_ai_result(fast_analysis.result)
    except AiBudgetExceeded as exc:
        _record_budget_block(listing, str(exc))
        return None
    except AiProviderError as exc:
        if exc.code == "AI_INVALID_OUTPUT":
            fast_schema_failed = True
        else:
            _set_listing_state(listing, AnalysisState.FAILED)
            return None

    final = fast_analysis
    escalate, reason = should_escalate(
        fast_result,
        listing,
        escalation_confidence=state.ai_escalation_confidence,
        high_value_profit=state.ai_high_value_profit_uah,
        fast_schema_failed=fast_schema_failed,
    )
    if escalate:
        try:
            deep_analysis = _run_tier(
                listing, AiTier.DEEP, client, revision=revision, force_reason=force_reason
            )
            final = deep_analysis
            logger.info(
                "ai_escalated",
                extra={"event": "ai_escalated", "listing_id": str(listing.id)},
            )
        except AiBudgetExceeded as exc:
            _record_budget_block(listing, str(exc))
            final = fast_analysis
        except AiProviderError:
            final = fast_analysis  # deep failed: keep fast result visible

    if final is not None and final.status == AiStatus.SUCCESS:
        _apply_to_listing(listing, final)
        return final
    _set_listing_state(listing, AnalysisState.FAILED)
    return None


def _apply_to_listing(listing: Listing, analysis: AiAnalysis) -> None:
    with transaction.atomic():
        Listing.objects.filter(pk=listing.pk).update(
            analysis_status=AnalysisState.SUCCESS,
            current_risk_level=analysis.risk_level,
        )
    listing.refresh_from_db()


def _set_listing_state(listing: Listing, state: str) -> None:
    Listing.objects.filter(pk=listing.pk).update(analysis_status=state)
    listing.refresh_from_db()


def _record_budget_block(listing: Listing, message: str) -> None:
    from apps.alerts.services import enqueue_system_incident

    logger.warning(
        "ai_budget_exceeded",
        extra={"event": "ai_budget_exceeded", "listing_id": str(listing.id)},
    )
    _set_listing_state(listing, AnalysisState.FAILED)
    enqueue_system_incident("AI_BUDGET_EXCEEDED", message)


def request_reanalysis(listing: Listing, *, force: bool = False, force_reason: str = "") -> dict:
    """Web-side queueing for POST /listings/{id}/reanalyze/.

    Returns {"queued": bool, "cache_hit": bool, "analysis_id", "revision"}.
    Never calls the provider synchronously.
    """
    from apps.analysis.selectors import running_analysis_exists

    if running_analysis_exists(listing):
        raise AiAlreadyRunning("Анализ уже выполняется.")

    if not force:
        cached_fast = find_cached_success(listing, AiTier.FAST, 0)
        if cached_fast is not None:
            cached_deep = find_cached_success(listing, AiTier.DEEP, 0)
            final = cached_deep or cached_fast
            _apply_to_listing(listing, final)
            return {
                "queued": False,
                "cache_hit": True,
                "analysis_id": str(final.id),
                "revision": final.revision,
            }
        revision = 0
    else:
        if not force_reason or not (5 <= len(force_reason) <= 255):
            raise ValueError("Для force-анализа нужна причина 5–255 символов.")
        revision = next_revision(listing, AiTier.FAST)
        if revision == 0 and find_cached_success(listing, AiTier.FAST, 0) is not None:
            revision = 1

    pending = create_analysis_row(
        listing, AiTier.FAST, revision=revision, force_reason=force_reason
    )
    _set_listing_state(listing, AnalysisState.PENDING)
    return {
        "queued": True,
        "cache_hit": False,
        "analysis_id": str(pending.id),
        "revision": revision,
    }


def process_pending_analyses(*, client=None, limit: int = 3) -> int:
    """Worker loop: execute queued (PENDING) analyses."""
    from apps.core.services import effective_ai

    pending_rows = list(
        AiAnalysis.objects.filter(status=AiStatus.PENDING)
        .select_related("listing")
        .order_by("created_at")[:limit]
    )
    if not pending_rows:
        return 0

    if not effective_ai():
        for row in pending_rows:
            _mark_failed(row, "AI_UNAVAILABLE", "AI выключен или не настроен.")
            _set_listing_state(row.listing, AnalysisState.FAILED)
        return 0

    if client is None:
        from apps.analysis.client import get_ai_client

        try:
            client = get_ai_client()
        except AiProviderError:
            return 0

    from apps.core.services import get_app_state

    state = get_app_state()
    done = 0
    for row in pending_rows:
        listing = row.listing
        try:
            check_budget()
            final = execute_analysis(row, client)
            result = validate_ai_result(final.result)
            escalate, _reason = should_escalate(
                result,
                listing,
                escalation_confidence=state.ai_escalation_confidence,
                high_value_profit=state.ai_high_value_profit_uah,
            )
            if escalate:
                try:
                    final = _run_tier(
                        listing,
                        AiTier.DEEP,
                        client,
                        revision=row.revision,
                        force_reason=row.force_reason,
                    )
                except (AiProviderError, AiBudgetExceeded):
                    pass
            _apply_to_listing(listing, final)
            done += 1
        except AiBudgetExceeded as exc:
            _mark_failed(row, "AI_BUDGET_EXCEEDED", str(exc))
            _record_budget_block(listing, str(exc))
        except AiProviderError:
            _set_listing_state(listing, AnalysisState.FAILED)
    return done


def ai_spend_summary() -> dict:
    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    return {
        "today_usd": str(spent_usd_since(day_start)),
        "month_usd": str(spent_usd_since(month_start)),
        "daily_limit_usd": str(settings.AI_DAILY_HARD_LIMIT_USD),
        "monthly_limit_usd": str(settings.AI_MONTHLY_HARD_LIMIT_USD),
        "pricing_verified_at": settings.OPENAI_PRICING_VERIFIED_AT,
    }
