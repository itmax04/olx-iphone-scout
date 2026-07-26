"""Deal form for HTML views. Financial math stays server-side in services."""

from django import forms

from apps.deals.enums import DealStatus
from apps.deals.models import Deal


class DealForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = [
            "status",
            "purchase_price_uah",
            "purchased_at",
            "acquisition_shipping_uah",
            "repair_cost_uah",
            "other_cost_uah",
            "sale_price_uah",
            "sold_at",
            "notes",
        ]
        labels = {
            "status": "Статус",
            "purchase_price_uah": "Цена покупки, грн",
            "purchased_at": "Дата покупки",
            "acquisition_shipping_uah": "Доставка при покупке, грн",
            "repair_cost_uah": "Ремонт, грн",
            "other_cost_uah": "Прочие расходы, грн",
            "sale_price_uah": "Цена продажи, грн",
            "sold_at": "Дата продажи",
            "notes": "Заметки",
        }
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "purchase_price_uah": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "purchased_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "acquisition_shipping_uah": forms.NumberInput(
                attrs={"class": "form-control", "min": "0"}
            ),
            "repair_cost_uah": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "other_cost_uah": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "sale_price_uah": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "sold_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": "3", "maxlength": "5000"}
            ),
        }

    def clean(self):
        cleaned = super().clean() or {}
        status = cleaned.get("status")
        if status == DealStatus.SOLD:
            if not cleaned.get("sale_price_uah"):
                self.add_error("sale_price_uah", "Укажите цену продажи.")
            if not cleaned.get("sold_at"):
                self.add_error("sold_at", "Укажите дату продажи.")
            purchased_at = cleaned.get("purchased_at")
            sold_at = cleaned.get("sold_at")
            if purchased_at and sold_at and sold_at < purchased_at:
                self.add_error("sold_at", "Дата продажи не может быть раньше даты покупки.")
        return cleaned
