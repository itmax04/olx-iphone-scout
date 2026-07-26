"""Access control: single Administrator role."""

from django.contrib.auth.mixins import UserPassesTestMixin
from rest_framework.permissions import BasePermission


def is_administrator(user: object) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "is_superuser", False)
    )


class IsAdministrator(BasePermission):
    """Allows access only to the active superuser; is_staff alone is not enough."""

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        return is_administrator(request.user)


class AdministratorRequiredMixin(UserPassesTestMixin):
    """HTML pages: anonymous users are redirected to login, others get 403."""

    def test_func(self) -> bool:
        return is_administrator(self.request.user)  # type: ignore[attr-defined]
