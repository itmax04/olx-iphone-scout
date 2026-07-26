"""Local development settings: DEBUG allowed, relaxed cookies, plain static files."""

from config.settings.base import *  # noqa: F401,F403
from config.settings.base import env_bool

DEBUG = env_bool("DJANGO_DEBUG", default=True)

if not SECRET_KEY:  # noqa: F405
    # Local-only fallback so a first run works before .env is filled in.
    SECRET_KEY = "local-development-only-insecure-key"  # noqa: S105

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Manifest storage breaks when static files change between collectstatic runs
# during development, so use the plain storage locally.
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
