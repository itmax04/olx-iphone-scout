"""Core views: authentication, health, error handlers and the API envelope."""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LogoutView
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.enums import AuditAction, ErrorCode
from apps.core.exceptions import ApiError, RateLimitedError
from apps.core.forms import LoginForm
from apps.core.models import AppState
from apps.core.permissions import is_administrator
from apps.core.services import record_audit

logger = logging.getLogger(__name__)


# ---------- Authentication ----------


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if is_administrator(request.user):
        return redirect("dashboard:index")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"]
        password = form.cleaned_data["password"]
        remember = form.cleaned_data["remember"]
        user = authenticate(request, username=identifier, password=password)
        if user is not None and user.is_active:
            login(request, user)
            if remember:
                request.session.set_expiry(settings.REMEMBER_SESSION_AGE)
            else:
                request.session.set_expiry(0)
            record_audit(action=AuditAction.LOGIN_SUCCESS, actor=user, request=request)
            next_url = request.POST.get("next") or request.GET.get("next") or ""
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect("dashboard:index")
        # Neutral failure message; axes counts the failure via the signal.
        try:
            record_audit(action=AuditAction.LOGIN_FAILURE, request=request)
        except Exception:  # pragma: no cover - audit must not break login
            logger.warning("login_failure_audit_failed", extra={"event": "audit_failed"})
        form.add_error(None, "Неверный логин или пароль.")

    next_value = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_value = ""
    return render(request, "registration/login.html", {"form": form, "next": next_value})


class SafeLogoutView(LogoutView):
    next_page = "/accounts/login/"


@require_http_methods(["GET", "POST"])
def password_change_view(request: HttpRequest) -> HttpResponse:
    if not is_administrator(request.user):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        return render(request, "403.html", status=403)

    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        record_audit(action=AuditAction.PASSWORD_CHANGED, actor=user, request=request)
        messages.success(request, "Пароль изменен.")
        return redirect("dashboard:index")
    return render(request, "registration/password_change_form.html", {"form": form})


# ---------- Health ----------


def health_live(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "web"})


def health_ready(request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "not_ready", "database": "unavailable"}, status=503)
    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            return JsonResponse({"status": "not_ready", "database": "schema_pending"}, status=503)
    except Exception:
        return JsonResponse({"status": "not_ready", "database": "schema_pending"}, status=503)
    try:
        if not AppState.objects.filter(pk=1).exists():
            return JsonResponse(
                {"status": "not_ready", "database": "app_state_missing"}, status=503
            )
    except Exception:
        return JsonResponse({"status": "not_ready", "database": "app_state_missing"}, status=503)
    return JsonResponse(
        {"status": "ready", "database": "ok", "schema": "current", "app_state": "ok"}
    )


# ---------- Error pages ----------


def permission_denied_view(request: HttpRequest, exception: Exception) -> HttpResponse:
    return render(request, "403.html", status=403)


def page_not_found_view(request: HttpRequest, exception: Exception) -> HttpResponse:
    return render(request, "404.html", status=404)


def server_error_view(request: HttpRequest) -> HttpResponse:
    return render(request, "500.html", status=500)


# ---------- DRF error envelope ----------


def api_exception_handler(exc: Exception, context: dict) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", "") if request is not None else ""

    code: str = ErrorCode.INTERNAL_ERROR
    message = "Произошла ошибка."
    field_errors: dict[str, list[str]] | None = None

    if isinstance(exc, ApiError):
        code = str(exc.error_code)
        message = str(exc.detail)
    elif isinstance(exc, drf_exceptions.ValidationError):
        code = ErrorCode.VALIDATION_ERROR
        message = "Проверьте заполненные поля."
        detail = exc.detail
        if isinstance(detail, dict):
            field_errors = {
                str(field): [
                    str(item) for item in (errors if isinstance(errors, list) else [errors])
                ]
                for field, errors in detail.items()
            }
        elif isinstance(detail, list):
            message = "; ".join(str(item) for item in detail) or message
    elif isinstance(exc, drf_exceptions.NotAuthenticated | drf_exceptions.AuthenticationFailed):
        code = ErrorCode.AUTH_REQUIRED
        message = "Требуется вход."
        response.status_code = 403
    elif isinstance(exc, drf_exceptions.PermissionDenied):
        code = ErrorCode.PERMISSION_DENIED
        message = "Недостаточно прав."
    elif isinstance(exc, drf_exceptions.NotFound):
        code = ErrorCode.NOT_FOUND
        message = "Объект не найден."
    elif isinstance(exc, drf_exceptions.MethodNotAllowed):
        code = ErrorCode.METHOD_NOT_ALLOWED
        message = "Метод не поддерживается."
    elif isinstance(exc, drf_exceptions.UnsupportedMediaType):
        code = ErrorCode.VALIDATION_ERROR
        message = "Неподдерживаемый Content-Type."
    elif isinstance(exc, drf_exceptions.ParseError):
        code = ErrorCode.VALIDATION_ERROR
        message = "Некорректный JSON."
    elif isinstance(exc, drf_exceptions.Throttled):
        code = ErrorCode.RATE_LIMITED
        message = "Слишком много запросов."

    envelope: dict[str, object] = {
        "error": {
            "code": str(code),
            "message": message,
            "request_id": request_id,
        }
    }
    if field_errors:
        envelope["error"]["field_errors"] = field_errors  # type: ignore[index]

    response.data = envelope
    if isinstance(exc, RateLimitedError):
        response["Retry-After"] = str(exc.retry_after)
    return response
