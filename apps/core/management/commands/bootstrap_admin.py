"""Idempotent creation of the single administrator account from environment."""

import os

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Create the administrator account from ADMIN_USERNAME/ADMIN_EMAIL/ADMIN_PASSWORD. "
        "Never changes the password of an existing account."
    )

    def handle(self, *args: object, **options: object) -> None:
        user_model = get_user_model()
        username = (os.environ.get("ADMIN_USERNAME") or "").strip()
        email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
        password = os.environ.get("ADMIN_PASSWORD") or ""

        if user_model.objects.filter(is_superuser=True, is_active=True).exists():
            self.stdout.write(self.style.SUCCESS("bootstrap_admin: administrator already exists"))
            return

        if not username or not email or not password:
            raise CommandError(
                "bootstrap_admin: ADMIN_USERNAME, ADMIN_EMAIL and ADMIN_PASSWORD are required "
                "for the first run (no administrator exists yet)."
            )

        try:
            validate_email(email)
        except ValidationError:
            raise CommandError("bootstrap_admin: ADMIN_EMAIL is not a valid email address")

        probe = user_model(username=username, email=email)
        try:
            password_validation.validate_password(password, user=probe)
        except ValidationError as exc:
            raise CommandError(
                "bootstrap_admin: ADMIN_PASSWORD is too weak: " + "; ".join(exc.messages)
            )

        if user_model.objects.filter(email__iexact=email).exclude(email="").exists():
            raise CommandError(
                "bootstrap_admin: a user with this email already exists but is not an "
                "active administrator; resolve manually"
            )
        if user_model.objects.filter(username__iexact=username).exists():
            raise CommandError(
                "bootstrap_admin: a user with this username already exists but is not an "
                "active administrator; resolve manually"
            )

        with transaction.atomic():
            user_model.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(
            self.style.SUCCESS(f"bootstrap_admin: administrator '{username}' created")
        )
