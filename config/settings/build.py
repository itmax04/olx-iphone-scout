"""Build-time settings used only for `collectstatic` inside the Docker build.

This module must never read production secrets and must never serve HTTP.
"""

from config.settings.base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = "build-only-not-a-runtime-secret"  # noqa: S105

ALLOWED_HOSTS = ["build.invalid"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "build_placeholder",
        "USER": "build_placeholder",
        "PASSWORD": "build_placeholder",
        "HOST": "127.0.0.1",
        "PORT": "5432",
    }
}

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
