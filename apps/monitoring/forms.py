"""Monitoring forms: SearchProfile create/edit."""

from django import forms
from django.core.exceptions import ValidationError

from apps.monitoring.models import SearchProfile
from apps.monitoring.validators import canonicalize_olx_url, validate_olx_url
from apps.pricing.constants import ALLOWED_STORAGE_GB, MODEL_CHOICES

STORAGE_CHOICES = tuple((str(v), f"{v} GB" if v != 1024 else "1 TB") for v in ALLOWED_STORAGE_GB)


class KeywordsField(forms.CharField):
    """Comma-separated keywords -> list[str], max 20 items of 40 chars."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault(
            "widget",
            forms.TextInput(attrs={"class": "form-control", "placeholder": "слово1, слово2"}),
        )
        super().__init__(**kwargs)

    def to_python(self, value):
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return value
        items = [item.strip() for item in str(value).split(",")]
        items = [item for item in items if item]
        if len(items) > 20:
            raise ValidationError("Максимум 20 слов.")
        for item in items:
            if len(item) > 40:
                raise ValidationError(f"Слово «{item[:40]}…» длиннее 40 символов.")
        return items

    def prepare_value(self, value):
        if isinstance(value, list):
            return ", ".join(value)
        return value


class SearchProfileForm(forms.ModelForm):
    target_models = forms.MultipleChoiceField(
        label="Целевые модели",
        choices=MODEL_CHOICES,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "8"}),
    )
    target_storage_gb = forms.MultipleChoiceField(
        label="Память",
        choices=STORAGE_CHOICES,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "5"}),
    )
    included_keywords = KeywordsField(label="Включить слова (все должны встречаться)")
    excluded_keywords = KeywordsField(label="Исключить слова")

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
        labels = {
            "name": "Название",
            "olx_url": "URL выдачи OLX",
            "is_active": "Активен",
            "min_price_uah": "Цена от, грн",
            "max_purchase_price_uah": "Максимальная закупка, грн",
            "min_expected_profit_uah": "Минимальная прибыль, грн",
            "min_roi_percent": "Минимальный ROI, %",
            "private_only": "Только частные продавцы",
            "delivery_required": "Требовать OLX Доставку",
            "interval_seconds": "Интервал, секунд",
            "jitter_seconds": "Jitter, секунд",
            "max_cards": "Карточек за скан",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "maxlength": "80"}),
            "olx_url": forms.Textarea(attrs={"class": "form-control", "rows": "3"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "min_price_uah": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "max_purchase_price_uah": forms.NumberInput(
                attrs={"class": "form-control", "min": "1"}
            ),
            "min_expected_profit_uah": forms.NumberInput(
                attrs={"class": "form-control", "min": "0"}
            ),
            "min_roi_percent": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "max": "100", "step": "0.01"}
            ),
            "private_only": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "delivery_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "interval_seconds": forms.NumberInput(
                attrs={"class": "form-control", "min": "60", "max": "3600"}
            ),
            "jitter_seconds": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "max": "60"}
            ),
            "max_cards": forms.NumberInput(
                attrs={"class": "form-control", "min": "5", "max": "50"}
            ),
        }

    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Введите название.")
        return name

    def clean_olx_url(self) -> str:
        url = self.cleaned_data.get("olx_url") or ""
        return validate_olx_url(url)

    def clean_target_models(self) -> list[str]:
        return list(self.cleaned_data["target_models"])

    def clean_target_storage_gb(self) -> list[int]:
        return [int(v) for v in self.cleaned_data["target_storage_gb"]]

    def clean(self):
        cleaned = super().clean()
        min_price = cleaned.get("min_price_uah")
        max_price = cleaned.get("max_purchase_price_uah")
        if min_price is not None and max_price is not None and max_price <= min_price:
            self.add_error("max_purchase_price_uah", "Введите сумму больше минимальной цены.")
        url = cleaned.get("olx_url")
        if url:
            canonical = canonicalize_olx_url(url)
            existing = SearchProfile.objects.filter(canonical_url=canonical)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                self.add_error("olx_url", "Профиль с таким URL уже существует.")
            cleaned["canonical_url"] = canonical
        return cleaned

    def save(self, commit: bool = True):
        profile = super().save(commit=False)
        profile.canonical_url = self.cleaned_data["canonical_url"]
        if commit:
            profile.save()
        return profile
