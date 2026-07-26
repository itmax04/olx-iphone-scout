"""Case-insensitive username-or-email authentication backend.

The backend never reveals whether an account exists: every failure path
returns None and the login form shows one neutral message.
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

logger = logging.getLogger(__name__)


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(  # type: ignore[override]
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: object,
    ):
        if not username or not password:
            return None
        user_model = get_user_model()
        identifier = username.strip()
        user = None
        try:
            user = user_model.objects.get(username__iexact=identifier)
        except user_model.DoesNotExist:
            if "@" in identifier:
                matches = list(user_model.objects.filter(email__iexact=identifier)[:2])
                if len(matches) == 1:
                    user = matches[0]
                elif len(matches) > 1:
                    # Fail closed: ambiguous email match is a data problem,
                    # not a login opportunity.
                    logger.warning(
                        "auth_ambiguous_email_match",
                        extra={"event": "auth_ambiguous_email_match"},
                    )
                    return None
        except user_model.MultipleObjectsReturned:
            logger.warning(
                "auth_ambiguous_username_match",
                extra={"event": "auth_ambiguous_username_match"},
            )
            return None

        if user is None:
            # Equalize timing with a dummy hash check.
            user_model().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
