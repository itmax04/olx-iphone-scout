"""JSON API for deals (§12.9)."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers as drf_serializers
from rest_framework.views import APIView

from apps.core.api_helpers import data_response, list_response
from apps.deals.enums import DealStatus
from apps.deals.models import Deal
from apps.deals.services import create_deal, update_deal
from apps.monitoring.models import Listing

WRITE_FIELDS = {
    "listing_id",
    "status",
    "purchase_price_uah",
    "purchased_at",
    "acquisition_shipping_uah",
    "repair_cost_uah",
    "other_cost_uah",
    "sale_price_uah",
    "sold_at",
    "notes",
    "expected_updated_at",
}


class DealInputSerializer(drf_serializers.Serializer):
    listing_id = drf_serializers.UUIDField(required=False)
    status = drf_serializers.ChoiceField(choices=DealStatus.choices, required=False)
    purchase_price_uah = drf_serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    purchased_at = drf_serializers.DateTimeField(required=False)
    acquisition_shipping_uah = drf_serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    repair_cost_uah = drf_serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    other_cost_uah = drf_serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    sale_price_uah = drf_serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    sold_at = drf_serializers.DateTimeField(required=False, allow_null=True)
    notes = drf_serializers.CharField(required=False, allow_blank=True, max_length=5000)
    expected_updated_at = drf_serializers.CharField(required=False)


def _check_unknown(data: dict) -> None:
    unknown = set(data.keys()) - WRITE_FIELDS
    if unknown:
        raise drf_serializers.ValidationError(
            {field: ["Неизвестное поле."] for field in sorted(unknown)}
        )


def serialize_deal(deal: Deal) -> dict:
    return {
        "id": str(deal.id),
        "listing_id": str(deal.listing_id),
        "listing_title": deal.listing.title,
        "status": deal.status,
        "purchase_price_uah": str(deal.purchase_price_uah),
        "purchased_at": deal.purchased_at.isoformat(),
        "acquisition_shipping_uah": str(deal.acquisition_shipping_uah),
        "repair_cost_uah": str(deal.repair_cost_uah),
        "other_cost_uah": str(deal.other_cost_uah),
        "sale_price_uah": str(deal.sale_price_uah) if deal.sale_price_uah is not None else None,
        "sold_at": deal.sold_at.isoformat() if deal.sold_at else None,
        "realized_profit_uah": str(deal.realized_profit_uah)
        if deal.realized_profit_uah is not None
        else None,
        "purchase_snapshot": deal.purchase_snapshot,
        "listing_status_before_purchase": deal.listing_status_before_purchase,
        "source_evaluation_id": str(deal.source_evaluation_id)
        if deal.source_evaluation_id
        else None,
        "notes": deal.notes,
        "updated_at": deal.updated_at.isoformat(),
    }


class DealListApi(APIView):
    def get(self, request):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.deals.views import deals_queryset

        try:
            qs = deals_queryset(request.query_params.dict())
        except DjangoValidationError as exc:
            raise drf_serializers.ValidationError(getattr(exc, "message_dict", exc.messages))
        return list_response(qs, request, serialize_deal)

    def post(self, request):
        _check_unknown(request.data)
        serializer = DealInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        listing_id = payload.pop("listing_id", None)
        if listing_id is None:
            raise drf_serializers.ValidationError({"listing_id": ["Обязательное поле."]})
        listing = get_object_or_404(Listing, pk=listing_id)
        payload.pop("status", None)
        payload.pop("expected_updated_at", None)
        deal = create_deal(listing, payload, actor=request.user, request=request)
        return data_response(serialize_deal(deal), status=201)


class DealDetailApi(APIView):
    def get(self, request, pk):
        deal = get_object_or_404(Deal.objects.select_related("listing"), pk=pk)
        return data_response(serialize_deal(deal))

    def patch(self, request, pk):
        deal = get_object_or_404(Deal.objects.select_related("listing"), pk=pk)
        _check_unknown(request.data)
        if "realized_profit_uah" in request.data:
            raise drf_serializers.ValidationError({"realized_profit_uah": ["Неизвестное поле."]})
        serializer = DealInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        payload.pop("listing_id", None)
        expected = payload.pop("expected_updated_at", None)
        deal = update_deal(
            deal, payload, expected_updated_at=expected, actor=request.user, request=request
        )
        return data_response(serialize_deal(deal))
