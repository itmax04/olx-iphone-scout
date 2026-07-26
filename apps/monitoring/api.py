"""JSON API for search profiles, listings and scan runs (§12.5, §12.8, §12.10)."""

import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers as drf_serializers
from rest_framework.views import APIView

from apps.core.api_helpers import data_response, list_response, reject_unknown_fields
from apps.core.enums import AuditAction, ErrorCode
from apps.core.exceptions import ApiError, ConflictError, PreconditionError
from apps.core.services import record_audit
from apps.monitoring.collectors.exceptions import CollectorError
from apps.monitoring.models import Listing, ScanRun, SearchProfile
from apps.monitoring.selectors import (
    listings_queryset,
    scan_runs_queryset,
    search_profiles_queryset,
)
from apps.monitoring.serializers import (
    SearchProfileWriteSerializer,
    serialize_listing_detail,
    serialize_listing_row,
    serialize_profile,
    serialize_scan_run,
)
from apps.monitoring.status_machine import change_status


def _django_to_drf(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise drf_serializers.ValidationError(exc.message_dict)
    raise drf_serializers.ValidationError(exc.messages)


class SearchProfileListApi(APIView):
    def get(self, request):
        try:
            qs = search_profiles_queryset(request.query_params.dict())
        except DjangoValidationError as exc:
            _django_to_drf(exc)
        return list_response(qs, request, serialize_profile)

    def post(self, request):
        serializer = SearchProfileWriteSerializer(data=request.data)
        reject_unknown_fields(serializer)
        serializer.is_valid(raise_exception=True)
        try:
            profile = serializer.save(created_by=request.user)
        except IntegrityError:
            raise ConflictError("Профиль с таким canonical URL уже существует.")
        record_audit(
            action=AuditAction.SEARCH_PROFILE_CREATED,
            actor=request.user,
            target_type="SearchProfile",
            target_id=str(profile.id),
            request=request,
        )
        return data_response(serialize_profile(profile), status=201)


class SearchProfileDetailApi(APIView):
    def get_object(self, pk) -> SearchProfile:
        return get_object_or_404(SearchProfile, pk=pk)

    def get(self, request, pk):
        return data_response(serialize_profile(self.get_object(pk)))

    def patch(self, request, pk):
        profile = self.get_object(pk)
        if profile.is_running and "olx_url" in request.data:
            raise ConflictError("Профиль сейчас сканируется; URL менять нельзя.")
        serializer = SearchProfileWriteSerializer(profile, data=request.data, partial=True)
        reject_unknown_fields(serializer)
        serializer.is_valid(raise_exception=True)
        try:
            profile = serializer.save()
        except IntegrityError:
            raise ConflictError("Профиль с таким canonical URL уже существует.")
        record_audit(
            action=AuditAction.SEARCH_PROFILE_UPDATED,
            actor=request.user,
            target_type="SearchProfile",
            target_id=str(profile.id),
            request=request,
        )
        return data_response(serialize_profile(profile))

    def delete(self, request, pk):
        profile = self.get_object(pk)
        from apps.monitoring.services import archive_profile

        archive_profile(profile, actor=request.user, request=request)
        return HttpResponse(status=204)


class SearchProfileTestApi(APIView):
    def post(self, request):
        url = request.data.get("olx_url", "")
        max_cards = request.data.get("max_cards", 5)
        unknown = set(request.data.keys()) - {"olx_url", "max_cards"}
        if unknown:
            raise drf_serializers.ValidationError(
                {field: ["Неизвестное поле."] for field in sorted(unknown)}
            )
        from apps.monitoring.services import test_search_url

        try:
            result = test_search_url(url, max_cards=max_cards, actor=request.user, request=request)
        except DjangoValidationError as exc:
            _django_to_drf(exc)
        except CollectorError as exc:
            if exc.error_code in (ErrorCode.OLX_TIMEOUT,):
                raise ApiError(exc.safe_message, code=exc.error_code)
            raise ConflictError(exc.safe_message)
        return data_response(result)


class SearchProfileRunApi(APIView):
    def post(self, request, pk):
        profile = get_object_or_404(SearchProfile, pk=pk)
        from apps.monitoring.services import queue_manual_run

        result = queue_manual_run(profile, actor=request.user, request=request)
        return data_response(result, status=202)


class ListingListApi(APIView):
    def get(self, request):
        try:
            qs = listings_queryset(request.query_params.dict())
        except DjangoValidationError as exc:
            _django_to_drf(exc)
        return list_response(qs, request, serialize_listing_row)


class ListingDetailApi(APIView):
    def get(self, request, pk):
        listing = get_object_or_404(Listing.objects.select_related("current_evaluation"), pk=pk)
        return data_response(serialize_listing_detail(listing))


class ListingStatusApi(APIView):
    def patch(self, request, pk):
        listing = get_object_or_404(Listing, pk=pk)
        allowed = {"status", "note", "expected_current_status"}
        unknown = set(request.data.keys()) - allowed
        if unknown:
            raise drf_serializers.ValidationError(
                {field: ["Неизвестное поле."] for field in sorted(unknown)}
            )
        listing = change_status(
            listing,
            new_status=request.data.get("status"),
            note=request.data.get("note"),
            expected_current_status=request.data.get("expected_current_status"),
            actor=request.user,
            request=request,
        )
        return data_response(
            {
                "id": str(listing.id),
                "decision_status": listing.decision_status,
                "manual_notes": listing.manual_notes,
                "updated_at": listing.updated_at.isoformat(),
            }
        )


class ListingReanalyzeApi(APIView):
    def post(self, request, pk):
        listing = get_object_or_404(Listing, pk=pk)
        allowed = {"reason", "force"}
        unknown = set(request.data.keys()) - allowed
        if unknown:
            raise drf_serializers.ValidationError(
                {field: ["Неизвестное поле."] for field in sorted(unknown)}
            )
        from apps.analysis.services import AiAlreadyRunning, request_reanalysis
        from apps.core.services import effective_ai, enforce_rate_limit

        if not effective_ai():
            raise PreconditionError("AI выключен или не настроен.")
        if not listing.is_active:
            raise ConflictError("Объявление неактивно.")
        force = bool(request.data.get("force", False))
        reason = (request.data.get("reason") or "").strip()
        enforce_rate_limit(AuditAction.REANALYZE_REQUESTED, "REANALYZE", request.user)
        try:
            result = request_reanalysis(listing, force=force, force_reason=reason)
        except AiAlreadyRunning:
            raise ConflictError("Анализ уже выполняется.")
        except ValueError as exc:
            raise drf_serializers.ValidationError({"reason": [str(exc)]})
        record_audit(
            action=AuditAction.REANALYZE_REQUESTED,
            actor=request.user,
            target_type="Listing",
            target_id=str(listing.id),
            changes={"force": force},
            request=request,
        )
        if result["cache_hit"]:
            return data_response(
                {"queued": False, "cache_hit": True, "analysis_id": result["analysis_id"]}
            )
        return data_response(
            {
                "queued": True,
                "analysis_status": "PENDING",
                "revision": result["revision"],
            },
            status=202,
        )


class ScanRunListApi(APIView):
    def get(self, request):
        try:
            qs = scan_runs_queryset(request.query_params.dict())
        except DjangoValidationError as exc:
            _django_to_drf(exc)
        return list_response(qs, request, serialize_scan_run)


class ScanRunDetailApi(APIView):
    def get(self, request, pk):
        run = get_object_or_404(ScanRun, pk=pk)
        return data_response(serialize_scan_run(run))


class ScanRunDiagnosticApi(APIView):
    def get(self, request, pk):
        run = get_object_or_404(ScanRun, pk=pk)
        payload = serialize_scan_run(run)  # already safe: no HTML/env/cookies
        response = HttpResponse(
            json.dumps({"data": payload}, ensure_ascii=False, indent=2),
            content_type="application/json",
        )
        response["Content-Disposition"] = f'attachment; filename="scan-run-{run.id}.json"'
        return response
