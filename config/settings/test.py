"""Test settings: deterministic, fast, никаких внешних вызовов."""

from config.settings.base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = "test-only-not-a-real-secret-0123456789abcdef"  # noqa: S105

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Fast hasher for tests; the dedicated security test overrides this to verify
# that the production hasher list starts with Argon2.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Never talk to real integrations from tests.
MONITOR_ENABLED = False
AI_ENABLED = False
OPENAI_API_KEY = ""
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

LOGGING = {}
