"""DRF serializers for pricing rules."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.pricing.constants import ALLOWED_STORAGE_GB, DEFECT_CODES, MODEL_REGISTRY
from apps.pricing.models import DefectReserveRule, MarketPriceRule


class MarketPriceRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketPriceRule
        fields = [
            "model_key",
            "storage_gb",
            "sim_variant",
            "expected_final_sale_price_uah",
            "acquisition_shipping_uah",
            "other_cost_reserve_uah",
            "checked_at",
            "is_active",
        ]
        validators: list = []  # unique ловится IntegrityError -> 409 по контракту §12

    def validate_model_key(self, value: str) -> str:
        if value not in MODEL_REGISTRY:
            raise serializers.ValidationError("Неизвестная модель.")
        return value

    def validate_storage_gb(self, value: int) -> int:
        if value not in ALLOWED_STORAGE_GB:
            raise serializers.ValidationError("Недопустимая память.")
        return value

    def validate_expected_final_sale_price_uah(self, value):
        if value <= 0:
            raise serializers.ValidationError("Цена продажи должна быть больше нуля.")
        return value

    def validate_acquisition_shipping_uah(self, value):
        if value < 0:
            raise serializers.ValidationError("Сумма не может быть отрицательной.")
        return value

    def validate_other_cost_reserve_uah(self, value):
        if value < 0:
            raise serializers.ValidationError("Сумма не может быть отрицательной.")
        return value

    def validate_checked_at(self, value):
        if value > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError("Дата проверки не может быть в будущем.")
        return value

    def validate(self, attrs):
        model_key = attrs.get("model_key", getattr(self.instance, "model_key", None))
        storage = attrs.get("storage_gb", getattr(self.instance, "storage_gb", None))
        if model_key and storage and storage not in MODEL_REGISTRY[model_key]["storage"]:
            raise serializers.ValidationError(
                {"storage_gb": ["Такой памяти не существует для выбранной модели."]}
            )
        return attrs


def serialize_market_rule(rule: MarketPriceRule) -> dict:
    return {
        "id": str(rule.id),
        "model_key": rule.model_key,
        "storage_gb": rule.storage_gb,
        "sim_variant": rule.sim_variant,
        "expected_final_sale_price_uah": str(rule.expected_final_sale_price_uah),
        "acquisition_shipping_uah": str(rule.acquisition_shipping_uah),
        "other_cost_reserve_uah": str(rule.other_cost_reserve_uah),
        "checked_at": rule.checked_at.isoformat(),
        "is_active": rule.is_active,
    }


class DefectReserveRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DefectReserveRule
        fields = [
            "code",
            "model_key",
            "label",
            "amount_uah",
            "exclusive_group",
            "priority",
            "is_active",
        ]
        validators: list = []  # unique -> 409
        extra_kwargs = {"model_key": {"required": False, "allow_blank": True}}

    def validate_code(self, value: str) -> str:
        if value not in DEFECT_CODES:
            raise serializers.ValidationError("Код вне allowlist дефектов.")
        return value

    def validate_model_key(self, value: str) -> str:
        if value and value not in MODEL_REGISTRY:
            raise serializers.ValidationError("Неизвестная модель.")
        return value or ""

    def validate_amount_uah(self, value):
        if value < 0:
            raise serializers.ValidationError("Сумма не может быть отрицательной.")
        return value

    def validate_priority(self, value: int) -> int:
        if not 0 <= value <= 1000:
            raise serializers.ValidationError("Приоритет 0–1000.")
        return value


def serialize_defect_rule(rule: DefectReserveRule) -> dict:
    return {
        "id": str(rule.id),
        "code": rule.code,
        "model_key": rule.model_key,
        "label": rule.label,
        "amount_uah": str(rule.amount_uah),
        "exclusive_group": rule.exclusive_group,
        "priority": rule.priority,
        "is_active": rule.is_active,
    }
