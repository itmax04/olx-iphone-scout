"""Deterministic pricing services: prefilter, formula profit-v1, evaluations.

AI never participates in these numbers. All money math is Decimal.
"""

import hashlib
import json
import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.analysis.enums import EvaluationDecision
from apps.analysis.models import Evaluation
from apps.monitoring.enums import DecisionStatus, RiskLevel
from apps.monitoring.models import Listing, SearchProfile
from apps.pricing.constants import DEFECT_CODES, MODEL_REGISTRY
from apps.pricing.extraction import (
    classify_item_type,
    detect_defects,
    detect_lock_flags,
    extract_model,
    extract_storage,
)
from apps.pricing.models import DefectReserveRule, MarketPriceRule
from apps.pricing.types import AppliedReserve, CalculationResult, ExtractionResult

logger = logging.getLogger(__name__)

MONEY_Q = Decimal("0.01")
BORDERLINE_FACTOR = Decimal("0.90")  # within 10% below a threshold -> manual review


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


# ---------- Extraction ----------


def extract_listing_facts(title: str, description: str | None) -> ExtractionResult:
    text = f"{title}\n{description or ''}"
    model_key, ambiguous = extract_model(text)
    storage = extract_storage(text)
    item_type, item_codes = classify_item_type(title)
    lock_hard, lock_manual = detect_lock_flags(text)
    defects = detect_defects(text)

    hard: list[str] = list(item_codes) + list(lock_hard)
    manual: list[str] = list(lock_manual)

    storage_valid = True
    if model_key and storage is not None:
        storage_valid = storage in MODEL_REGISTRY[model_key]["storage"]

    from apps.pricing.extraction import extract_battery_percent

    return ExtractionResult(
        model_key=model_key,
        model_ambiguous=ambiguous,
        storage_gb=storage,
        storage_valid=storage_valid,
        item_type=item_type,
        defect_codes=defects,
        battery_percent=extract_battery_percent(text),
        hard_stop_codes=tuple(dict.fromkeys(hard)),
        manual_codes=tuple(dict.fromkeys(manual)),
    )


# ---------- Prefilter ----------


def prefilter(
    listing: Listing, profile: SearchProfile, facts: ExtractionResult
) -> tuple[str, list[str]]:
    """Return (decision, reason_codes) before any economics.

    decision: CONTINUE / REJECT / MANUAL_REVIEW.
    """
    codes: list[str] = []

    if facts.hard_stop_codes:
        return EvaluationDecision.REJECT, list(facts.hard_stop_codes)

    if listing.current_price_uah is None:
        return EvaluationDecision.REJECT, ["PRICE_MISSING"]
    if listing.currency != "UAH":
        return EvaluationDecision.REJECT, ["CURRENCY_UNSUPPORTED"]

    if facts.model_ambiguous:
        return EvaluationDecision.MANUAL_REVIEW, ["MODEL_AMBIGUOUS"]
    if facts.model_key is None or facts.model_key not in MODEL_REGISTRY:
        return EvaluationDecision.REJECT, ["MODEL_UNSUPPORTED"]
    if profile.target_models and facts.model_key not in profile.target_models:
        return EvaluationDecision.REJECT, ["MODEL_UNSUPPORTED"]

    text = f"{listing.title}\n{listing.description or ''}".lower()
    for word in profile.excluded_keywords or []:
        if word and word.lower() in text:
            return EvaluationDecision.REJECT, ["KEYWORD_EXCLUDED"]
    for word in profile.included_keywords or []:
        if word and word.lower() not in text:
            return EvaluationDecision.REJECT, ["KEYWORD_MISSING"]

    if profile.private_only and listing.seller_type == "BUSINESS":
        return EvaluationDecision.REJECT, ["SELLER_TYPE_MISMATCH"]

    if listing.current_price_uah < profile.min_price_uah:
        return EvaluationDecision.REJECT, ["PRICE_BELOW_MINIMUM"]

    if facts.storage_gb is None or not facts.storage_valid:
        return EvaluationDecision.MANUAL_REVIEW, ["STORAGE_UNKNOWN"]
    if profile.target_storage_gb and facts.storage_gb not in profile.target_storage_gb:
        return EvaluationDecision.REJECT, ["STORAGE_MISMATCH"]

    if profile.delivery_required:
        if listing.delivery_available is False:
            return EvaluationDecision.REJECT, ["DELIVERY_MISSING"]
        if listing.delivery_available is None:
            codes.append("DELIVERY_UNKNOWN")

    if facts.manual_codes:
        codes.extend(facts.manual_codes)

    if codes:
        return EvaluationDecision.MANUAL_REVIEW, codes
    return "CONTINUE", []


# ---------- Rule selection ----------


def select_market_rule(model_key: str, storage_gb: int) -> tuple[MarketPriceRule | None, bool]:
    """Return (rule, is_stale). SIM preference: exact variant beats ANY."""
    from apps.core.services import get_app_state

    rules = list(
        MarketPriceRule.objects.filter(
            is_active=True, model_key=model_key, storage_gb=storage_gb
        ).order_by("sim_variant")
    )
    if not rules:
        return None, False
    rule = next((r for r in rules if r.sim_variant == "ANY"), rules[0])
    stale_days = get_app_state().market_price_stale_days
    is_stale = rule.checked_at < timezone.now() - timedelta(days=stale_days)
    return rule, is_stale


def select_defect_reserves(
    model_key: str, defect_codes: tuple[str, ...]
) -> tuple[list[AppliedReserve], list[str]]:
    """Match defect codes to active reserve rules.

    Model-specific rules override universal; mutually exclusive groups apply
    once (highest priority wins). Returns (applied, missing_codes).
    """
    if not defect_codes:
        return [], []
    rules = DefectReserveRule.objects.filter(
        is_active=True, code__in=defect_codes, model_key__in=["", model_key]
    )
    by_code: dict[str, DefectReserveRule] = {}
    for rule in rules:
        current = by_code.get(rule.code)
        if current is None or (rule.model_key and not current.model_key):
            by_code[rule.code] = rule

    missing = [code for code in defect_codes if code not in by_code]

    # Apply exclusive groups: keep one rule per group with the highest priority.
    selected: dict[str, DefectReserveRule] = {}
    group_best: dict[str, DefectReserveRule] = {}
    for code, rule in by_code.items():
        group = DEFECT_CODES.get(code, {}).get("exclusive_group") or rule.exclusive_group
        if group:
            best = group_best.get(group)
            if best is None or rule.priority > best.priority:
                group_best[group] = rule
        else:
            selected[code] = rule
    for rule in group_best.values():
        selected[rule.code] = rule

    applied = [
        AppliedReserve(
            code=rule.code,
            label=rule.label,
            amount_uah=money(rule.amount_uah),
            rule_id=str(rule.id),
            model_specific=bool(rule.model_key),
        )
        for rule in sorted(selected.values(), key=lambda r: r.code)
    ]
    return applied, missing


# ---------- Formula profit-v1 ----------


def calculate(
    purchase_price: Decimal,
    rule: MarketPriceRule | None,
    applied_reserves: list[AppliedReserve],
    min_expected_profit: Decimal,
    profile_max_price: Decimal,
) -> CalculationResult:
    defect_reserve = money(sum((r.amount_uah for r in applied_reserves), Decimal("0")))
    shipping = money(rule.acquisition_shipping_uah) if rule else Decimal("0.00")
    other = money(rule.other_cost_reserve_uah) if rule else Decimal("0.00")
    total_reserve = money(shipping + other + defect_reserve)
    investment = money(purchase_price + total_reserve)

    sale = money(rule.expected_final_sale_price_uah) if rule else None
    profit = money(sale - purchase_price - total_reserve) if sale is not None else None

    roi: Decimal | None = None
    if profit is not None and investment > 0:
        roi = (profit / investment * Decimal("100")).quantize(MONEY_Q, rounding=ROUND_HALF_UP)

    calculated_max = money(sale - total_reserve - min_expected_profit) if sale is not None else None
    effective_max = (
        min(money(profile_max_price), calculated_max)
        if calculated_max is not None
        else money(profile_max_price)
    )

    return CalculationResult(
        expected_sale_price_uah=sale,
        shipping_reserve_uah=shipping,
        defect_reserve_uah=defect_reserve,
        other_reserve_uah=other,
        total_reserve_uah=total_reserve,
        expected_total_investment_uah=investment,
        expected_profit_uah=profit,
        roi_percent=roi,
        calculated_max_purchase_price_uah=calculated_max,
        effective_max_purchase_price_uah=effective_max,
        applied_reserves=tuple(applied_reserves),
    )


def _economics_decision(
    price: Decimal,
    calc: CalculationResult,
    profile: SearchProfile,
) -> tuple[str, list[str]]:
    codes: list[str] = []
    profit = calc.expected_profit_uah
    roi = calc.roi_percent
    effective_max = calc.effective_max_purchase_price_uah
    min_profit = money(profile.min_expected_profit_uah)
    min_roi = profile.min_roi_percent

    if profit is None:
        return EvaluationDecision.MANUAL_REVIEW, ["MARKET_PRICE_MISSING"]

    price_ok = effective_max is None or price <= effective_max
    profit_ok = profit >= min_profit
    roi_ok = roi is not None and roi >= min_roi

    if price_ok and profit_ok and roi_ok:
        return EvaluationDecision.CANDIDATE, ["PROFIT_THRESHOLD_MET", "ROI_THRESHOLD_MET"]

    # Borderline: every threshold within 10%, none catastrophically missed.
    profit_border = profit >= money(min_profit * BORDERLINE_FACTOR)
    roi_border = roi is not None and (min_roi == 0 or roi >= (min_roi * BORDERLINE_FACTOR))
    if price_ok and profit_border and roi_border:
        return EvaluationDecision.MANUAL_REVIEW, ["PRICE_BORDERLINE"]

    if not price_ok:
        codes.append("ABOVE_EFFECTIVE_MAX_PRICE")
    if not profit_ok:
        codes.append("PROFIT_BELOW_THRESHOLD")
    if not roi_ok:
        codes.append("ROI_BELOW_THRESHOLD")
    return EvaluationDecision.REJECT, codes


# ---------- Evaluation ----------


def _input_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def evaluate_listing_for_profile(
    listing: Listing,
    profile: SearchProfile,
    *,
    snapshot=None,
    ai_analysis=None,
) -> Evaluation:
    """Create (or reuse) the deterministic Evaluation for listing+profile."""
    facts = extract_listing_facts(listing.title, listing.description)
    decision, codes = prefilter(listing, profile, facts)

    price = money(listing.current_price_uah) if listing.current_price_uah is not None else None
    rule: MarketPriceRule | None = None
    applied: list[AppliedReserve] = []

    if decision == "CONTINUE":
        assert price is not None and facts.model_key is not None and facts.storage_gb is not None
        rule, is_stale = select_market_rule(facts.model_key, facts.storage_gb)
        applied, missing_codes = select_defect_reserves(facts.model_key, facts.defect_codes)
        calc = calculate(
            price,
            rule,
            applied,
            money(profile.min_expected_profit_uah),
            money(profile.max_purchase_price_uah),
        )
        if rule is None:
            decision, codes = EvaluationDecision.MANUAL_REVIEW, ["MARKET_PRICE_MISSING"]
        elif missing_codes:
            decision = EvaluationDecision.MANUAL_REVIEW
            codes = ["RESERVE_RULE_MISSING"] + missing_codes
        elif is_stale:
            decision, codes = EvaluationDecision.MANUAL_REVIEW, ["MARKET_PRICE_STALE"]
        else:
            decision, codes = _economics_decision(price, calc, profile)
    else:
        calc = calculate(
            price if price is not None else Decimal("0.00"),
            None,
            [],
            money(profile.min_expected_profit_uah),
            money(profile.max_purchase_price_uah),
        )

    input_hash = _input_hash(
        {
            "formula": settings.PROFIT_FORMULA_VERSION,
            "listing": str(listing.id),
            "snapshot": snapshot.id if snapshot is not None else None,
            "profile": str(profile.id),
            "price": price,
            "content_hash": listing.content_hash,
            "rule": {
                "id": str(rule.id) if rule else None,
                "sale": rule.expected_final_sale_price_uah if rule else None,
                "shipping": rule.acquisition_shipping_uah if rule else None,
                "other": rule.other_cost_reserve_uah if rule else None,
                "checked_at": rule.checked_at.isoformat() if rule else None,
            },
            "reserves": [(r.code, r.amount_uah, r.rule_id) for r in applied],
            "thresholds": {
                "max": profile.max_purchase_price_uah,
                "min_profit": profile.min_expected_profit_uah,
                "min_roi": profile.min_roi_percent,
                "min_price": profile.min_price_uah,
            },
            "decision": decision,
            "codes": sorted(codes),
        }
    )

    existing = Evaluation.objects.filter(listing=listing, input_hash=input_hash).first()
    if existing is not None:
        return existing

    try:
        with transaction.atomic():
            evaluation = Evaluation.objects.create(
                listing=listing,
                listing_snapshot=snapshot,
                search_profile=profile,
                ai_analysis=ai_analysis,
                market_price_rule=rule,
                formula_version=settings.PROFIT_FORMULA_VERSION,
                input_hash=input_hash,
                purchase_price_uah=price if price is not None else Decimal("0.00"),
                expected_sale_price_uah=calc.expected_sale_price_uah,
                shipping_reserve_uah=calc.shipping_reserve_uah,
                defect_reserve_uah=calc.defect_reserve_uah,
                other_reserve_uah=calc.other_reserve_uah,
                total_reserve_uah=calc.total_reserve_uah,
                expected_total_investment_uah=calc.expected_total_investment_uah,
                expected_profit_uah=calc.expected_profit_uah,
                roi_percent=calc.roi_percent,
                profile_max_purchase_price_uah=money(profile.max_purchase_price_uah),
                calculated_max_purchase_price_uah=calc.calculated_max_purchase_price_uah,
                effective_max_purchase_price_uah=calc.effective_max_purchase_price_uah,
                required_min_profit_uah=money(profile.min_expected_profit_uah),
                required_min_roi_percent=profile.min_roi_percent,
                decision=decision,
                reason_codes=list(codes),
                applied_reserves=[
                    {
                        "code": r.code,
                        "label": r.label,
                        "amount_uah": str(r.amount_uah),
                        "rule_id": r.rule_id,
                        "model_specific": r.model_specific,
                    }
                    for r in applied
                ],
            )
    except IntegrityError:
        evaluation = Evaluation.objects.get(listing=listing, input_hash=input_hash)
    return evaluation


# ---------- Current evaluation selection (§6.7.3) ----------

_DECISION_PRIORITY = {
    EvaluationDecision.CANDIDATE: 0,
    EvaluationDecision.MANUAL_REVIEW: 1,
    EvaluationDecision.REJECT: 2,
}


def select_current_evaluation(listing: Listing) -> Evaluation | None:
    """Pick Listing.current_evaluation deterministically and copy summary fields."""
    latest_snapshot = listing.snapshots.order_by("-observed_at", "-id").first()
    candidates = list(
        Evaluation.objects.filter(
            listing=listing,
            formula_version=settings.PROFIT_FORMULA_VERSION,
            search_profile__is_active=True,
            search_profile__archived_at__isnull=True,
        ).select_related("search_profile", "ai_analysis")
    )
    if latest_snapshot is not None:
        candidates = [e for e in candidates if e.listing_snapshot_id in (latest_snapshot.id, None)]

    def sort_key(evaluation: Evaluation):
        profit = evaluation.expected_profit_uah
        roi = evaluation.roi_percent
        return (
            _DECISION_PRIORITY.get(evaluation.decision, 3),
            0 if profit is not None else 1,
            -(profit if profit is not None else Decimal("0")),
            0 if roi is not None else 1,
            -(roi if roi is not None else Decimal("0")),
            -evaluation.created_at.timestamp(),
            str(evaluation.search_profile_id or ""),
        )

    chosen = min(candidates, key=sort_key) if candidates else None

    with transaction.atomic():
        current = Listing.objects.select_for_update().get(pk=listing.pk)
        if chosen is None:
            current.current_evaluation = None
            current.current_expected_sale_price_uah = None
            current.current_total_reserve_uah = None
            current.current_expected_total_investment_uah = None
            current.current_expected_profit_uah = None
            current.current_roi_percent = None
            current.current_effective_max_purchase_price_uah = None
            current.current_is_candidate = False
            if current.decision_status == DecisionStatus.CANDIDATE:
                current.decision_status = DecisionStatus.NEW
        else:
            current.current_evaluation = chosen
            current.current_expected_sale_price_uah = chosen.expected_sale_price_uah
            current.current_total_reserve_uah = chosen.total_reserve_uah
            current.current_expected_total_investment_uah = chosen.expected_total_investment_uah
            current.current_expected_profit_uah = chosen.expected_profit_uah
            current.current_roi_percent = chosen.roi_percent
            current.current_effective_max_purchase_price_uah = (
                chosen.effective_max_purchase_price_uah
            )
            current.current_is_candidate = chosen.decision == EvaluationDecision.CANDIDATE
            if chosen.ai_analysis and chosen.ai_analysis.risk_level != RiskLevel.UNKNOWN:
                current.current_risk_level = chosen.ai_analysis.risk_level
            # Worker-driven decision_status transitions (never override manual states).
            if chosen.decision == EvaluationDecision.CANDIDATE and current.decision_status in (
                DecisionStatus.NEW,
                DecisionStatus.SKIPPED,
            ):
                current.decision_status = DecisionStatus.CANDIDATE
            elif chosen.decision == EvaluationDecision.REJECT and _is_hard_stop(chosen):
                if current.decision_status in (DecisionStatus.NEW, DecisionStatus.CANDIDATE):
                    current.decision_status = DecisionStatus.SKIPPED
            elif current.decision_status == DecisionStatus.CANDIDATE and chosen.decision in (
                EvaluationDecision.REJECT,
                EvaluationDecision.MANUAL_REVIEW,
            ):
                current.decision_status = DecisionStatus.NEW
        current.save()
    listing.refresh_from_db()
    return chosen


def _is_hard_stop(evaluation: Evaluation) -> bool:
    from apps.pricing.constants import HARD_STOP_CODES

    return any(code in HARD_STOP_CODES for code in evaluation.reason_codes or [])
