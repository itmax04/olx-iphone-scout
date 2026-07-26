"""DRF serializers for monitoring resources. Explicit fields only."""

from rest_framework import serializers

from apps.monitoring.models import Listing, ScanRun, SearchProfile
from apps.monitoring.validators import canonicalize_olx_url, validate_olx_url
from apps.pricing.constants import ALLOWED_STORAGE_GB, MODEL_REGISTRY


class SearchProfileWriteSerializer(serializers.ModelSerializer):
    olx_url = serializers.CharField(max_length=2048)
    target_models = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    target_storage_gb = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    included_keywords = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, max_length=20
    )
    excluded_keywords = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, max_length=20
    )

    class Meta:
        model = SearchProfile
        fields = [
            "name",
            "olx_url",
            "is_active",
            "target_models",
            "target_storage_gb",
            "min_price_uah",
            "max_purchase_price_uah",
            "min_expected_profit_uah",
            "min_roi_percent",
            "private_only",
            "delivery_required",
            "interval_seconds",
            "jitter_seconds",
            "max_cards",
            "included_keywords",
            "excluded_keywords",
        ]

    def validate_olx_url(self, value: str) -> str:
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            return validate_olx_url(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)

    def validate_target_models(self, value: list[str]) -> list[str]:
        for model_key in value:
            if model_key not in MODEL_REGISTRY:
                raise serializers.ValidationError(f"Неизвестная модель: {model_key}")
        return value

    def validate_target_storage_gb(self, value: list[int]) -> list[int]:
        for storage in value:
            if storage not in ALLOWED_STORAGE_GB:
                raise serializers.ValidationError(f"Недопустимая память: {storage}")
        return value

    def validate_interval_seconds(self, value: int) -> int:
        if not 60 <= value <= 3600:
            raise serializers.ValidationError("Интервал 60–3600 секунд.")
        return value

    def validate_jitter_seconds(self, value: int) -> int:
        if not 0 <= value <= 60:
            raise serializers.ValidationError("Jitter 0–60 секунд.")
        return value

    def validate_max_cards(self, value: int) -> int:
        if not 5 <= value <= 50:
            raise serializers.ValidationError("Карточек за скан: 5–50.")
        return value

    def validate(self, attrs):
        min_price = attrs.get("min_price_uah", getattr(self.instance, "min_price_uah", 0))
        max_price = attrs.get(
            "max_purchase_price_uah", getattr(self.instance, "max_purchase_price_uah", None)
        )
        if max_price is not None and min_price is not None and max_price <= min_price:
            raise serializers.ValidationError(
                {"max_purchase_price_uah": ["Введите сумму больше минимальной цены."]}
            )
        url = attrs.get("olx_url")
        if url:
            attrs["canonical_url"] = canonicalize_olx_url(url)
        return attrs


def serialize_profile(profile: SearchProfile) -> dict:
    return {
        "id": str(profile.id),
        "name": profile.name,
        "olx_url": profile.olx_url,
        "canonical_url": profile.canonical_url,
        "is_active": profile.is_active,
        "archived_at": profile.archived_at.isoformat() if profile.archived_at else None,
        "target_models": profile.target_models,
        "target_storage_gb": profile.target_storage_gb,
        "min_price_uah": str(profile.min_price_uah),
        "max_purchase_price_uah": str(profile.max_purchase_price_uah),
        "min_expected_profit_uah": str(profile.min_expected_profit_uah),
        "min_roi_percent": str(profile.min_roi_percent),
        "private_only": profile.private_only,
        "delivery_required": profile.delivery_required,
        "interval_seconds": profile.interval_seconds,
        "jitter_seconds": profile.jitter_seconds,
        "max_cards": profile.max_cards,
        "included_keywords": profile.included_keywords,
        "excluded_keywords": profile.excluded_keywords,
        "next_scan_at": profile.next_scan_at.isoformat() if profile.next_scan_at else None,
        "last_success_at": profile.last_success_at.isoformat() if profile.last_success_at else None,
        "consecutive_failures": profile.consecutive_failures,
        "last_error_code": profile.last_error_code,
        "is_running": profile.is_running,
    }


def serialize_listing_row(listing: Listing) -> dict:
    return {
        "id": str(listing.id),
        "olx_id": listing.olx_id,
        "title": listing.title,
        "canonical_url": listing.canonical_url,
        "model_key": listing.model_key or None,
        "storage_gb": listing.storage_gb,
        "current_price_uah": str(listing.current_price_uah)
        if listing.current_price_uah is not None
        else None,
        "current_expected_profit_uah": str(listing.current_expected_profit_uah)
        if listing.current_expected_profit_uah is not None
        else None,
        "current_roi_percent": str(listing.current_roi_percent)
        if listing.current_roi_percent is not None
        else None,
        "current_risk_level": listing.current_risk_level,
        "current_is_candidate": listing.current_is_candidate,
        "decision_status": listing.decision_status,
        "is_active": listing.is_active,
        "first_seen_at": listing.first_seen_at.isoformat(),
        "last_seen_at": listing.last_seen_at.isoformat(),
    }


def serialize_evaluation(evaluation) -> dict:
    return {
        "id": str(evaluation.id),
        "decision": evaluation.decision,
        "reason_codes": evaluation.reason_codes,
        "formula_version": evaluation.formula_version,
        "search_profile": str(evaluation.search_profile_id)
        if evaluation.search_profile_id
        else None,
        "purchase_price_uah": str(evaluation.purchase_price_uah),
        "expected_sale_price_uah": str(evaluation.expected_sale_price_uah)
        if evaluation.expected_sale_price_uah is not None
        else None,
        "total_reserve_uah": str(evaluation.total_reserve_uah),
        "expected_total_investment_uah": str(evaluation.expected_total_investment_uah),
        "expected_profit_uah": str(evaluation.expected_profit_uah)
        if evaluation.expected_profit_uah is not None
        else None,
        "roi_percent": str(evaluation.roi_percent) if evaluation.roi_percent is not None else None,
        "effective_max_purchase_price_uah": str(evaluation.effective_max_purchase_price_uah)
        if evaluation.effective_max_purchase_price_uah is not None
        else None,
        "applied_reserves": evaluation.applied_reserves,
        "created_at": evaluation.created_at.isoformat(),
    }


def serialize_listing_detail(listing: Listing) -> dict:
    from apps.analysis.selectors import latest_successful_analysis

    data = serialize_listing_row(listing)
    analysis = latest_successful_analysis(listing)
    data.update(
        {
            "description": listing.description,
            "location": listing.location,
            "seller_name": listing.seller_name,
            "seller_type": listing.seller_type,
            "seller_joined_text": listing.seller_joined_text,
            "delivery_available": listing.delivery_available,
            "photo_urls": listing.photo_urls,
            "manual_notes": listing.manual_notes,
            "analysis_status": listing.analysis_status,
            "current_evaluation_id": str(listing.current_evaluation_id)
            if listing.current_evaluation_id
            else None,
            "source_search_profile": str(listing.current_evaluation.search_profile_id)
            if listing.current_evaluation and listing.current_evaluation.search_profile_id
            else None,
            "current_evaluation": serialize_evaluation(listing.current_evaluation)
            if listing.current_evaluation
            else None,
            "evaluations": [
                serialize_evaluation(evaluation)
                for evaluation in listing.evaluations.order_by("-created_at")[:20]
            ],
            "snapshots": [
                {
                    "source": snapshot.source,
                    "price_uah": str(snapshot.price_uah)
                    if snapshot.price_uah is not None
                    else None,
                    "changed_fields": snapshot.changed_fields,
                    "observed_at": snapshot.observed_at.isoformat(),
                }
                for snapshot in listing.snapshots.order_by("-observed_at")[:30]
            ],
            "discoveries": [
                {
                    "search_profile": str(discovery.search_profile_id),
                    "first_seen_at": discovery.first_seen_at.isoformat(),
                }
                for discovery in listing.discoveries.all()
            ],
            "alerts": [
                {
                    "event_type": alert.event_type,
                    "status": alert.status,
                    "created_at": alert.created_at.isoformat(),
                }
                for alert in listing.outbox_items.order_by("-created_at")[:20]
            ],
            "ai_analysis": {
                "tier": analysis.tier,
                "confidence": str(analysis.confidence) if analysis.confidence else None,
                "risk_level": analysis.risk_level,
                "result": analysis.result,
                "completed_at": analysis.completed_at.isoformat()
                if analysis.completed_at
                else None,
            }
            if analysis
            else None,
            "deal_id": str(listing.deal.id) if hasattr(listing, "deal") else None,
        }
    )
    return data


def serialize_scan_run(run: ScanRun) -> dict:
    return {
        "id": str(run.id),
        "search_profile": str(run.search_profile_id) if run.search_profile_id else None,
        "correlation_id": str(run.correlation_id),
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "found_count": run.found_count,
        "new_count": run.new_count,
        "changed_count": run.changed_count,
        "candidate_count": run.candidate_count,
        "retry_count": run.retry_count,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "parser_version": run.parser_version,
    }
