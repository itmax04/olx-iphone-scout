"""Production settings: fail closed, secure cookies, HSTS, JSON logs."""

import os

from django.core.exceptions import ImproperlyConfigured

from config.settings.base import *  # noqa: F401,F403
from config.settings.base import env, env_bool

DEBUG = False

if env_bool("DJANGO_DEBUG", default=False):
    raise ImproperlyConfigured("DJANGO_DEBUG must be false in production")

if not SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required in production")

if len(SECRET_KEY) < 50:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be at least 50 characters long")

if not os.environ.get("DATABASE_URL"):
    raise ImproperlyConfigured("DATABASE_URL is required in production")

_render_host = env.str("RENDER_EXTERNAL_HOSTNAME", default="")
if _render_host:
    if _render_host not in ALLOWED_HOSTS:  # noqa: F405
        ALLOWED_HOSTS.append(_render_host)  # noqa: F405
    _render_origin = f"https://{_render_host}"
    if _render_origin not in CSRF_TRUSTED_ORIGINS:  # noqa: F405
        CSRF_TRUSTED_ORIGINS.append(_render_origin)  # noqa: F405

if "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Wildcard ALLOWED_HOSTS is forbidden in production")

for _origin in CSRF_TRUSTED_ORIGINS:  # noqa: F405
    if not _origin.startswith("https://"):
        raise ImproperlyConfigured(
            f"Production CSRF trusted origins must use https://, got {_origin!r}"
        )

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
# По ТЗ §13.16 includeSubDomains/preload намеренно выключены: приложение живет
# на поддомене onrender.com, которым владелец не управляет целиком.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

CONTENT_SECURITY_POLICY["DIRECTIVES"]["upgrade-insecure-requests"] = True  # noqa: F405
