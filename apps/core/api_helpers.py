"""Shared helpers for the JSON API envelope and strict input validation."""

from django.core.paginator import Paginator
from rest_framework import serializers as drf_serializers
from rest_framework.response import Response


def reject_unknown_fields(serializer) -> None:
    if not isinstance(serializer.initial_data, dict):
        raise drf_serializers.ValidationError({"non_field_errors": ["Ожидается JSON-объект."]})
    unknown = set(serializer.initial_data.keys()) - set(serializer.fields.keys())
    if unknown:
        raise drf_serializers.ValidationError(
            {field: ["Неизвестное поле."] for field in sorted(unknown)}
        )


def data_response(payload, status: int = 200) -> Response:
    return Response({"data": payload}, status=status)


def list_response(queryset, request, serialize_fn, *, max_page_size: int = 100) -> Response:
    try:
        page_size = int(request.query_params.get("page_size", 25))
        page_number = int(request.query_params.get("page", 1))
    except ValueError:
        raise drf_serializers.ValidationError({"page": ["Введите целое число."]})
    if page_size < 1 or page_size > max_page_size:
        raise drf_serializers.ValidationError(
            {"page_size": [f"Допустимо от 1 до {max_page_size}."]}
        )
    paginator = Paginator(queryset, page_size)
    if page_number < 1 or (paginator.num_pages and page_number > max(paginator.num_pages, 1)):
        page_number = min(max(page_number, 1), max(paginator.num_pages, 1))
    page = paginator.get_page(page_number)
    return Response(
        {
            "data": [serialize_fn(obj) for obj in page.object_list],
            "meta": {
                "page": page.number,
                "page_size": page_size,
                "total": paginator.count,
                "pages": paginator.num_pages,
            },
        }
    )
