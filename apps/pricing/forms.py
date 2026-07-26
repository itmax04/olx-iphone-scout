"""Pricing forms."""

from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.pricing.constants import (
    ALLOWED_STORAGE_GB,
    DEFECT_CODE_CHOICES,
    MODEL_CHOICES,
    MODEL_REGISTRY,
)
from apps.pricing.models import DefectReserveRule, MarketPriceRule

STORAGE_CHOICES = tuple((v, f"{v} GB" if v != 1024 else "1 TB") for v in ALLOWED_STORAGE_GB)


class MarketPriceRuleForm(forms.ModelForm):
    model_key = forms.ChoiceField(
        label="Модель", choices=MODEL_CHOICES, widget=forms.Select(attrs={"class": "form-select"})
    )
    storage_gb = forms.TypedChoiceField(
        label="Память",
        choices=STORAGE_CHOICES,
        coerce=int,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

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
        labels = {
            "sim_variant": "SIM-вариант",
            "expected_final_sale_price_uah": "Ожидаемая конечная цена быстрой продажи, грн",
            "acquisition_shipping_uah": "Резерв доставки, грн",
            "other_cost_reserve_uah": "Прочий резерв, грн",
            "checked_at": "Проверена",
            "is_active": "Активна",
        }
        widgets = {
            "sim_variant": forms.Select(attrs={"class": "form-select"}),
            "expected_final_sale_price_uah": forms.NumberInput(
                attrs={"class": "form-control", "min": "1"}
            ),
            "acquisition_shipping_uah": forms.NumberInput(
                attrs={"class": "form-control", "min": "0"}
            ),
            "other_cost_reserve_uah": forms.NumberInput(
                attrs={"class": "form-control", "min": "0"}
            ),
            "checked_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_checked_at(self):
        checked_at = self.cleaned_data["checked_at"]
        if checked_at and checked_at > timezone.now() + timedelta(minutes=5):
            raise ValidationError("Дата проверки не может быть в будущем.")
        return checked_at

    def clean(self):
        cleaned = super().clean() or {}
        model_key = cleaned.get("model_key")
        storage = cleaned.get("storage_gb")
        if model_key and storage and storage not in MODEL_REGISTRY[model_key]["storage"]:
            self.add_error(
                "storage_gb",
                f"Такой памяти не существует для {MODEL_REGISTRY[model_key]['label']}.",
            )
        if model_key and storage and cleaned.get("sim_variant"):
            existing = MarketPriceRule.objects.filter(
                model_key=model_key, storage_gb=storage, sim_variant=cleaned["sim_variant"]
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError("Правило для этой комбинации уже существует.")
        return cleaned


class DefectReserveRuleForm(forms.ModelForm):
    code = forms.ChoiceField(
        label="Код дефекта",
        choices=DEFECT_CODE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    model_key = forms.ChoiceField(
        label="Модель (пусто = для всех)",
        choices=(("", "Все модели"),) + MODEL_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

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
        labels = {
            "label": "Название для интерфейса",
            "amount_uah": "Сумма резерва, грн",
            "exclusive_group": "Взаимоисключающая группа (например BATTERY)",
            "priority": "Приоритет (0–1000)",
            "is_active": "Активно",
        }
        widgets = {
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "amount_uah": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "exclusive_group": forms.TextInput(attrs={"class": "form-control"}),
            "priority": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "max": "1000"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_model_key(self) -> str:
        return self.cleaned_data.get("model_key") or ""

    def clean(self):
        cleaned = super().clean() or {}
        code = cleaned.get("code")
        model_key = cleaned.get("model_key") or ""
        if code:
            existing = DefectReserveRule.objects.filter(code=code, model_key=model_key)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError("Правило с таким кодом и моделью уже существует.")
        return cleaned
