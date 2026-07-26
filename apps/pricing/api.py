"""JSON API for market price and defect reserve rules (§12.6–12.7)."""

from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from apps.core.api_helpers import data_response, list_response, reject_unknown_fields
from apps.core.enums import AuditAction
from apps.core.exceptions import ConflictError
from apps.core.services import record_audit
from apps.pricing.models import DefectReserveRule, MarketPriceRule
from apps.pricing.serializers import (
    DefectReserveRuleSerializer,
    MarketPriceRuleSerializer,
    serialize_defect_rule,
    serialize_market_rule,
)


class MarketRuleListApi(APIView):
    def get(self, request):
        qs = MarketPriceRule.objects.order_by("model_key", "storage_gb", "sim_variant")
        model = request.query_params.get("model", "")
        if model:
            qs = qs.filter(model_key=model)
        active = request.query_params.get("active", "")
        if active in ("1", "true"):
            qs = qs.filter(is_active=True)
        return list_response(qs, request, serialize_market_rule)

    def post(self, request):
        serializer = MarketPriceRuleSerializer(data=request.data)
        reject_unknown_fields(serializer)
        serializer.is_valid(raise_exception=True)
        try:
            rule = serializer.save()
        except IntegrityError:
            raise ConflictError("Правило для этой комбинации уже существует.")
        record_audit(
            action=AuditAction.MARKET_RULE_CREATED,
            actor=request.user,
            target_type="MarketPriceRule",
            target_id=str(rule.id),
            request=request,
        )
        return data_response(serialize_market_rule(rule), status=201)


class MarketRuleDetailApi(APIView):
    def get(self, request, pk):
        return data_response(serialize_market_rule(get_object_or_404(MarketPriceRule, pk=pk)))

    def patch(self, request, pk):
        rule = get_object_or_404(MarketPriceRule, pk=pk)
        serializer = MarketPriceRuleSerializer(rule, data=request.data, partial=True)
        reject_unknown_fields(serializer)
        serializer.is_valid(raise_exception=True)
        try:
            rule = serializer.save()
        except IntegrityError:
            raise ConflictError("Правило для этой комбинации уже существует.")
        record_audit(
            action=AuditAction.MARKET_RULE_UPDATED,
            actor=request.user,
            target_type="MarketPriceRule",
            target_id=str(rule.id),
            request=request,
        )
        return data_response(serialize_market_rule(rule))

    def delete(self, request, pk):
        rule = get_object_or_404(MarketPriceRule, pk=pk)
        rule.is_active = False
        rule.save(update_fields=["is_active", "updated_at"])
        record_audit(
            action=AuditAction.MARKET_RULE_DEACTIVATED,
            actor=request.user,
            target_type="MarketPriceRule",
            target_id=str(rule.id),
            request=request,
        )
        return HttpResponse(status=204)


class DefectRuleListApi(APIView):
    def get(self, request):
        qs = DefectReserveRule.objects.order_by("code", "model_key")
        code = request.query_params.get("code", "")
        if code:
            qs = qs.filter(code=code)
        model = request.query_params.get("model", "")
        if model:
            qs = qs.filter(model_key=model)
        return list_response(qs, request, serialize_defect_rule)

    def post(self, request):
        serializer = DefectReserveRuleSerializer(data=request.data)
        reject_unknown_fields(serializer)
        serializer.is_valid(raise_exception=True)
        try:
            rule = serializer.save()
        except IntegrityError:
            raise ConflictError("Правило с таким кодом и моделью уже существует.")
        record_audit(
            action=AuditAction.DEFECT_RULE_CREATED,
            actor=request.user,
            target_type="DefectReserveRule",
            target_id=str(rule.id),
            request=request,
        )
        return data_response(serialize_defect_rule(rule), status=201)


class DefectRuleDetailApi(APIView):
    def get(self, request, pk):
        return data_response(serialize_defect_rule(get_object_or_404(DefectReserveRule, pk=pk)))

    def patch(self, request, pk):
        rule = get_object_or_404(DefectReserveRule, pk=pk)
        serializer = DefectReserveRuleSerializer(rule, data=request.data, partial=True)
        reject_unknown_fields(serializer)
        serializer.is_valid(raise_exception=True)
        try:
            rule = serializer.save()
        except IntegrityError:
            raise ConflictError("Правило с таким кодом и моделью уже существует.")
        record_audit(
            action=AuditAction.DEFECT_RULE_UPDATED,
            actor=request.user,
            target_type="DefectReserveRule",
            target_id=str(rule.id),
            request=request,
        )
        return data_response(serialize_defect_rule(rule))

    def delete(self, request, pk):
        rule = get_object_or_404(DefectReserveRule, pk=pk)
        rule.is_active = False
        rule.save(update_fields=["is_active", "updated_at"])
        record_audit(
            action=AuditAction.DEFECT_RULE_DEACTIVATED,
            actor=request.user,
            target_type="DefectReserveRule",
            target_id=str(rule.id),
            request=request,
        )
        return HttpResponse(status=204)
