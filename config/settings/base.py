"""Base settings shared by every environment.

Environment-specific modules (local/test/production/build) import from here
and override only the documented differences.
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

_TRUE_VALUES = {"true", "1"}
_FALSE_VALUES = {"false", "0"}


def env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var accepting only true/false/1/0."""
    raw = env.str(name, default=None)
    if raw is None or raw == "":
        return default
    lowered = raw.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ImproperlyConfigured(f"{name} must be one of true/false/1/0, got {raw!r}")


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.str(name, default=None)
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw.strip())
        except ValueError:
            raise ImproperlyConfigured(f"{name} must be an integer, got {raw!r}")
    if not minimum <= value <= maximum:
        raise ImproperlyConfigured(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def env_decimal(name: str, default: str) -> Decimal:
    raw = env.str(name, default=None)
    if raw is None or raw == "":
        raw = default
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        raise ImproperlyConfigured(f"{name} must be a decimal number, got {raw!r}")
    if value < 0:
        raise ImproperlyConfigured(f"{name} must be >= 0, got {value}")
    return value


def env_list(name: str, default: str) -> list[str]:
    raw = env.str(name, default=default)
    items = [item.strip() for item in raw.split(",")]
    cleaned = [item for item in items if item]
    if not cleaned:
        raise ImproperlyConfigured(f"{name} must contain at least one non-empty value")
    return cleaned


APP_ENV = env.str("APP_ENV", default="local")
APP_VERSION = "1.0.0"
RENDER_GIT_COMMIT = env.str("RENDER_GIT_COMMIT", default="")

SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="")

DEBUG = False

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", default="http://localhost:8000")

APP_BASE_URL = env.str("APP_BASE_URL", default="http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_htmx",
    "axes",
    "csp",
    "apps.core",
    "apps.dashboard",
    "apps.monitoring",
    "apps.pricing",
    "apps.analysis",
    "apps.alerts",
    "apps.deals",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        **env.db_url(
            "DATABASE_URL", default="postgresql://placeholder:placeholder@db:5432/placeholder"
        ),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", default=60, minimum=0, maximum=600),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "apps.core.authentication.UsernameOrEmailBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

SESSION_COOKIE_AGE = 43200  # 12 hours
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
REMEMBER_SESSION_AGE = 14 * 24 * 60 * 60  # 14 days

# django-axes
AXES_FAILURE_LIMIT = env_int("AXES_FAILURE_LIMIT", default=5, minimum=1, maximum=100)
AXES_COOLOFF_TIME = timedelta(
    minutes=env_int("AXES_COOLOFF_MINUTES", default=15, minimum=1, maximum=1440)
)
AXES_HANDLER = "axes.handlers.database.AxesDatabaseHandler"
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_HTTP_RESPONSE_CODE = 429
AXES_LOCKOUT_TEMPLATE = "registration/locked_out.html"

# Content Security Policy (django-csp >= 4.0 style)
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'",),
        "style-src": ("'self'",),
        "img-src": ("'self'", "https:", "data:"),
        "connect-src": ("'self'",),
        "font-src": ("'self'",),
        "object-src": ("'none'",),
        "base-uri": ("'self'",),
        "form-action": ("'self'",),
        "frame-ancestors": ("'none'",),
    }
}

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.core.permissions.IsAdministrator",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "apps.core.views.api_exception_handler",
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

LANGUAGE_CODE = "ru"
TIME_ZONE = env.str("TIME_ZONE", default="Europe/Kyiv")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---------- Worker and OLX ----------
MONITOR_ENABLED = env_bool("MONITOR_ENABLED", default=False)
WORKER_POLL_SECONDS = env_int("WORKER_POLL_SECONDS", default=5, minimum=1, maximum=60)
OUTBOX_POLL_SECONDS = env_int("OUTBOX_POLL_SECONDS", default=5, minimum=1, maximum=60)
WORKER_HEARTBEAT_SECONDS = env_int("WORKER_HEARTBEAT_SECONDS", default=30, minimum=5, maximum=300)
OLX_ALLOWED_HOSTS = env_list("OLX_ALLOWED_HOSTS", default="olx.ua,www.olx.ua")
OLX_MIN_INTERVAL_SECONDS = env_int("OLX_MIN_INTERVAL_SECONDS", default=60, minimum=60, maximum=3600)
OLX_DEFAULT_INTERVAL_SECONDS = env_int(
    "OLX_DEFAULT_INTERVAL_SECONDS", default=90, minimum=60, maximum=3600
)
OLX_DEFAULT_JITTER_SECONDS = env_int(
    "OLX_DEFAULT_JITTER_SECONDS", default=15, minimum=0, maximum=60
)
OLX_MAX_CARDS_PER_SCAN = env_int("OLX_MAX_CARDS_PER_SCAN", default=50, minimum=5, maximum=50)
OLX_MAX_CONCURRENCY = env_int("OLX_MAX_CONCURRENCY", default=1, minimum=1, maximum=1)
OLX_NAVIGATION_TIMEOUT_MS = env_int(
    "OLX_NAVIGATION_TIMEOUT_MS", default=25000, minimum=1000, maximum=120000
)
OLX_BROWSER_RESTART_AFTER_SCANS = env_int(
    "OLX_BROWSER_RESTART_AFTER_SCANS", default=100, minimum=1, maximum=10000
)
PLAYWRIGHT_HEADLESS = env_bool("PLAYWRIGHT_HEADLESS", default=True)

# ---------- Runtime AI ----------
AI_ENABLED = env_bool("AI_ENABLED", default=False)
OPENAI_API_KEY = env.str("OPENAI_API_KEY", default="")
OPENAI_FAST_MODEL = env.str("OPENAI_FAST_MODEL", default="gpt-5.6-luna")
OPENAI_DEEP_MODEL = env.str("OPENAI_DEEP_MODEL", default="gpt-5.6-terra")
OPENAI_REASONING_EFFORT = env.str("OPENAI_REASONING_EFFORT", default="low")
OPENAI_TIMEOUT_SECONDS = env_int("OPENAI_TIMEOUT_SECONDS", default=30, minimum=1, maximum=300)
OPENAI_MAX_RETRIES = env_int("OPENAI_MAX_RETRIES", default=2, minimum=0, maximum=5)
AI_INPUT_MAX_CHARS = env_int("AI_INPUT_MAX_CHARS", default=12000, minimum=500, maximum=100000)
AI_SCHEMA_VERSION = env_int("AI_SCHEMA_VERSION", default=1, minimum=1, maximum=100)
AI_PROMPT_VERSION = env.str("AI_PROMPT_VERSION", default="iphone-risk-v1")
OPENAI_FAST_INPUT_USD_PER_MILLION = env_decimal("OPENAI_FAST_INPUT_USD_PER_MILLION", "1.00")
OPENAI_FAST_OUTPUT_USD_PER_MILLION = env_decimal("OPENAI_FAST_OUTPUT_USD_PER_MILLION", "6.00")
OPENAI_DEEP_INPUT_USD_PER_MILLION = env_decimal("OPENAI_DEEP_INPUT_USD_PER_MILLION", "2.50")
OPENAI_DEEP_OUTPUT_USD_PER_MILLION = env_decimal("OPENAI_DEEP_OUTPUT_USD_PER_MILLION", "15.00")
OPENAI_PRICING_VERIFIED_AT = env.str("OPENAI_PRICING_VERIFIED_AT", default="2026-07-24")
AI_DAILY_HARD_LIMIT_USD = env_decimal("AI_DAILY_HARD_LIMIT_USD", "1.00")
AI_MONTHLY_HARD_LIMIT_USD = env_decimal("AI_MONTHLY_HARD_LIMIT_USD", "10.00")

if AI_ENABLED:
    if AI_DAILY_HARD_LIMIT_USD <= 0 or AI_MONTHLY_HARD_LIMIT_USD <= 0:
        raise ImproperlyConfigured(
            "AI_DAILY_HARD_LIMIT_USD and AI_MONTHLY_HARD_LIMIT_USD must be positive "
            "when AI_ENABLED=true"
        )

# ---------- Telegram, outbound only ----------
TELEGRAM_BOT_TOKEN = env.str("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_CHAT_ID = env.str("TELEGRAM_CHAT_ID", default="")
TELEGRAM_TIMEOUT_SECONDS = env_int("TELEGRAM_TIMEOUT_SECONDS", default=15, minimum=1, maximum=120)

LOG_LEVEL = env.str("LOG_LEVEL", default="INFO")
LOG_FORMAT = env.str("LOG_FORMAT", default="text")
if LOG_FORMAT not in {"text", "json"}:
    raise ImproperlyConfigured(f"LOG_FORMAT must be 'text' or 'json', got {LOG_FORMAT!r}")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact": {"()": "apps.core.logging.RedactionFilter"},
    },
    "formatters": {
        "text": {"()": "apps.core.logging.TextFormatter"},
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["redact"],
            "formatter": LOG_FORMAT,
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.security.DisallowedHost": {"level": "WARNING"},
    },
}

# Rate limits (per user, enforced via AuditEvent windows)
RATE_LIMITS = {
    "SEARCH_URL_TEST": (3, 60),
    "MANUAL_RUN": (10, 60),
    "REANALYZE": (5, 60),
    "TELEGRAM_TEST": (3, 600),
    "CSV_EXPORT": (5, 600),
    "OPENAI_CHECK": (5, 60),
    "CLEANUP_PREVIEW": (3, 60),
}

PARSER_VERSION = "olx-dom-v1"
PROFIT_FORMULA_VERSION = "profit-v1"
WORKER_ADVISORY_LOCK_KEY = 815_501_137_242_001
