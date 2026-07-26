"""API exceptions carrying the standard error envelope codes."""

from rest_framework import status
from rest_framework.exceptions import APIException

from apps.core.enums import ErrorCode


class ApiError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = ErrorCode.VALIDATION_ERROR

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(detail=message)
        if code:
            self.error_code = code  # type: ignore[assignment]


class ConflictError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = ErrorCode.CONFLICT


class PreconditionError(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = ErrorCode.PRECONDITION_FAILED


class RateLimitedError(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = ErrorCode.RATE_LIMITED

    def __init__(self, message: str, *, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ServiceUnavailableError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = ErrorCode.DATABASE_UNAVAILABLE
