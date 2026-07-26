"""E-11/E-12: кандидат → связался → купил → продал; фактическая прибыль."""

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.deals.models import Deal
from apps.monitoring.models import Listing

pytestmark = pytest.mark.django_db


def test_candidate_to_sold_flow(admin_user):
    client = Client()
    client.force_login(admin_user)
    call_command("run_fixture_pipeline", stdout=open("/dev/null", "w"))
    listing = Listing.objects.get(olx_id="800000001")

    # Связался
    response = client.post(
        f"/listings/{listing.pk}/status/",
        {"status": "CONTACTED", "expected_current_status": "CANDIDATE", "note": ""},
    )
    assert response.status_code == 302

    # Купил: форма предзаполнена ценой объявления
    form_html = client.get(f"/deals/new/?listing={listing.pk}").content.decode()
    assert "11500" in form_html
    response = client.post(
        f"/deals/new/?listing={listing.pk}",
        {
            "listing": str(listing.pk),
            "status": "IN_STOCK",
            "purchase_price_uah": "11500",
            "purchased_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "acquisition_shipping_uah": "100",
            "repair_cost_uah": "500",
            "other_cost_uah": "100",
            "notes": "Проверен лично",
        },
    )
    assert response.status_code == 302
    listing.refresh_from_db()
    assert listing.decision_status == "BOUGHT"
    deal = Deal.objects.get()

    # Продал
    response = client.post(
        f"/deals/{deal.pk}/edit/",
        {
            "status": "SOLD",
            "purchase_price_uah": "11500",
            "purchased_at": deal.purchased_at.strftime("%Y-%m-%dT%H:%M"),
            "acquisition_shipping_uah": "100",
            "repair_cost_uah": "500",
            "other_cost_uah": "100",
            "sale_price_uah": "14500",
            "sold_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "notes": "Проверен лично",
            "expected_updated_at": deal.updated_at.isoformat(),
        },
    )
    assert response.status_code == 302
    deal.refresh_from_db()
    assert str(deal.realized_profit_uah) == "2300.00"
    listing.refresh_from_db()
    assert listing.decision_status == "SOLD"

    # Итоги в списке сделок
    html = client.get("/deals/").content.decode()
    assert "2 300" in html or "2300" in html
