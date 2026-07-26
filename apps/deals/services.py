"""Deal services: one Deal per Listing, immutable snapshot, server-side profit."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.enums import AuditAction
from apps.core.exceptions import ApiError, ConflictError
from apps.core.services import record_audit
from apps.deals.enums import DealStatus
from apps.deals.models import Deal
from apps.monitoring.enums import DecisionStatus
from apps.monitoring.models import Listing

ALLOWED_PRE_PURCHASE_STATUSES = {
    DecisionStatus.NEW,
    DecisionStatus.CANDIDATE,
    DecisionStatus.REVIEWED,
    DecisionStatus.CONTACTED,
    DecisionStatus.REJECTED,
    DecisionStatus.SKIPPED,
    DecisionStatus.ARCHIVED,
}


def compute_realized_profit(deal: Deal) -> Decimal | None:
    if deal.sale_price_uah is None:
        return None
    total_cost = (
        deal.purchase_price_uah
        + deal.acquisition_shipping_uah
        + deal.repair_cost_uah
        + deal.other_cost_uah
    )
    return (deal.sale_price_uah - total_cost).quantize(Decimal("0.01"))


def _build_purchase_snapshot(listing: Listing) -> dict:
    evaluation = listing.current_evaluation
    snapshot = listing.snapshots.order_by("-observed_at", "-id").first()
    return {
        "olx_id": listing.olx_id,
        "title": listing.title,
        "model_key": listing.model_key,
        "storage_gb": listing.storage_gb,
        "source_url": listing.canonical_url,
        "listing_snapshot_id": snapshot.id if snapshot else None,
        "source_evaluation_id": str(evaluation.id) if evaluation else None,
        "expected_profit_uah": str(listing.current_expected_profit_uah)
        if listing.current_expected_profit_uah is not None
        else None,
        "roi_percent": str(listing.current_roi_percent)
        if listing.current_roi_percent is not None
        else None,
        "captured_at": timezone.now().isoformat(),
    }


def _validate_financials(data: dict) -> None:
    if data.get("purchase_price_uah") is None or data["purchase_price_uah"] <= 0:
        raise ApiError("Цена покупки должна быть больше нуля.")
    for field in ("acquisition_shipping_uah", "repair_cost_uah", "other_cost_uah"):
        if data.get(field) is not None and data[field] < 0:
            raise ApiError("Суммы расходов не могут быть отрицательными.")


def _validate_sold(deal: Deal) -> None:
    if deal.sale_price_uah is None or deal.sale_price_uah <= 0:
        raise ApiError("Для статуса «Продано» укажите цену продажи больше нуля.")
    if deal.sold_at is None:
        raise ApiError("Для статуса «Продано» укажите дату продажи.")
    if deal.sold_at < deal.purchased_at:
        raise ApiError("Дата продажи не может быть раньше даты покупки.")


def create_deal(listing: Listing, data: dict, *, actor=None, request=None) -> Deal:
    """Create the single Deal for a listing (or reactivate a cancelled one)."""
    _validate_financials(data)

    with transaction.atomic():
        listing = Listing.objects.select_for_update().get(pk=listing.pk)
        existing = Deal.objects.select_for_update().filter(listing=listing).first()

        if existing is not None and existing.status != DealStatus.CANCELLED:
            raise ConflictError("У этого объявления уже есть сделка.")
        if listing.decision_status not in ALLOWED_PRE_PURCHASE_STATUSES:
            raise ConflictError(f"Нельзя создать сделку из статуса {listing.decision_status}.")

        status_before = listing.decision_status

        if existing is not None:
            # Re-activate the cancelled deal, never create a second one.
            deal = existing
            deal.status = DealStatus.IN_STOCK
            deal.purchase_price_uah = data["purchase_price_uah"]
            deal.purchased_at = data.get("purchased_at") or timezone.now()
            deal.acquisition_shipping_uah = data.get("acquisition_shipping_uah") or Decimal("0")
            deal.repair_cost_uah = data.get("repair_cost_uah") or Decimal("0")
            deal.other_cost_uah = data.get("other_cost_uah") or Decimal("0")
            deal.notes = data.get("notes", deal.notes)
            deal.sale_price_uah = None
            deal.sold_at = None
            deal.realized_profit_uah = None
            deal.listing_status_before_purchase = status_before
            deal.save()
        else:
            deal = Deal.objects.create(
                listing=listing,
                source_evaluation=listing.current_evaluation,
                listing_status_before_purchase=status_before,
                purchase_snapshot=_build_purchase_snapshot(listing),
                status=DealStatus.IN_STOCK,
                purchase_price_uah=data["purchase_price_uah"],
                purchased_at=data.get("purchased_at") or timezone.now(),
                acquisition_shipping_uah=data.get("acquisition_shipping_uah") or Decimal("0"),
                repair_cost_uah=data.get("repair_cost_uah") or Decimal("0"),
                other_cost_uah=data.get("other_cost_uah") or Decimal("0"),
                notes=data.get("notes", ""),
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
            )

        listing.decision_status = DecisionStatus.BOUGHT
        listing.save(update_fields=["decision_status", "updated_at"])
        record_audit(
            action=AuditAction.DEAL_CREATED,
            actor=actor,
            target_type="Deal",
            target_id=str(deal.id),
            changes={"purchase_price_uah": str(deal.purchase_price_uah)},
            request=request,
        )
    return deal


def update_deal(
    deal: Deal,
    data: dict,
    *,
    expected_updated_at=None,
    actor=None,
    request=None,
) -> Deal:
    """Update financials and/or transition IN_STOCK <-> CANCELLED / SOLD."""
    with transaction.atomic():
        deal = Deal.objects.select_for_update().select_related("listing").get(pk=deal.pk)
        listing = Listing.objects.select_for_update().get(pk=deal.listing_id)

        if expected_updated_at is not None:
            stored = deal.updated_at.replace(microsecond=0).isoformat()
            provided = str(expected_updated_at)[:19]
            if not provided or provided not in stored:
                raise ConflictError(
                    "Сделка была изменена в другом окне. Обновите страницу и повторите."
                )

        new_status = data.get("status", deal.status)
        if new_status not in DealStatus.values:
            raise ApiError("Недопустимый статус сделки.")

        if deal.status == DealStatus.SOLD and new_status != DealStatus.SOLD:
            raise ConflictError("Проданную сделку нельзя вернуть через обычный интерфейс.")

        for field in (
            "purchase_price_uah",
            "purchased_at",
            "acquisition_shipping_uah",
            "repair_cost_uah",
            "other_cost_uah",
            "sale_price_uah",
            "sold_at",
            "notes",
        ):
            if field in data and data[field] is not None:
                setattr(deal, field, data[field])

        _validate_financials(
            {
                "purchase_price_uah": deal.purchase_price_uah,
                "acquisition_shipping_uah": deal.acquisition_shipping_uah,
                "repair_cost_uah": deal.repair_cost_uah,
                "other_cost_uah": deal.other_cost_uah,
            }
        )

        changes: dict = {"status": {"from": deal.status, "to": new_status}}

        if new_status == DealStatus.SOLD:
            deal.status = DealStatus.SOLD
            _validate_sold(deal)
            deal.realized_profit_uah = compute_realized_profit(deal)
            listing.decision_status = DecisionStatus.SOLD
        elif new_status == DealStatus.CANCELLED:
            deal.status = DealStatus.CANCELLED
            deal.realized_profit_uah = None
            restore = deal.listing_status_before_purchase or DecisionStatus.CONTACTED
            listing.decision_status = restore
        elif new_status == DealStatus.IN_STOCK:
            if deal.status == DealStatus.CANCELLED:
                # Reactivation goes through create_deal contract.
                raise ConflictError(
                    "Отмененную сделку повторно активируйте через «Купил» на объявлении."
                )
            deal.status = DealStatus.IN_STOCK
            deal.realized_profit_uah = None
            listing.decision_status = DecisionStatus.BOUGHT

        deal.save()
        listing.save(update_fields=["decision_status", "updated_at"])
        record_audit(
            action=AuditAction.DEAL_UPDATED,
            actor=actor,
            target_type="Deal",
            target_id=str(deal.id),
            changes=changes,
            request=request,
        )
    return deal
