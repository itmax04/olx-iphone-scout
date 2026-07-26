"""OLX URL validation (SSRF-safe) and canonicalization.

Order matters: validate first, canonicalize only after validation passed.
"""

import ipaddress
import re
import socket
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core.exceptions import ValidationError

MAX_URL_LENGTH = 2048
MAX_QUERY_PAIRS = 100
MAX_QUERY_DECODED_CHARS = 4096

_TRACKING_KEYS = {
    "gclid",
    "fbclid",
    "yclid",
    "search_reason",
    "reason",
    "ref",
    "referrer",
    "campaign",
    "source",
}
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _is_tracking_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_KEYS


def _host_allowed(hostname: str) -> bool:
    """Exact allowed host or a subdomain of it; `olx.ua.evil.com` is rejected."""
    for allowed in settings.OLX_ALLOWED_HOSTS:
        base = allowed.lower().strip()
        if hostname == base or hostname.endswith("." + base):
            return True
    return False


def _resolve_and_check_public(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise ValidationError("Не удалось проверить DNS для адреса OLX. Повторите позже.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValidationError("Адрес OLX разрешается в недопустимую сеть.")


def validate_olx_url(url: str, *, check_dns: bool = True) -> str:
    """Validate an OLX search/detail URL. Returns the sanitized original URL."""
    url = (url or "").strip()
    if not url:
        raise ValidationError("Укажите ссылку на выдачу OLX.")
    if len(url) > MAX_URL_LENGTH:
        raise ValidationError("Ссылка длиннее 2048 символов.")
    if _CONTROL_CHARS.search(url):
        raise ValidationError("Ссылка содержит недопустимые символы.")

    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        raise ValidationError("Разрешены только HTTPS-ссылки.")
    if parts.username or parts.password:
        raise ValidationError("Ссылка не должна содержать логин или пароль.")

    hostname = parts.hostname or ""
    try:
        hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValidationError("Некорректное имя хоста.")
    if not _host_allowed(hostname):
        raise ValidationError("Разрешены только ссылки на olx.ua и его поддомены.")
    if parts.port is not None and parts.port != 443:
        raise ValidationError("Нестандартный порт запрещен.")

    if check_dns:
        _resolve_and_check_public(hostname)

    # Sanitized original: drop fragment only.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def canonicalize_olx_url(url: str) -> str:
    """Build the canonical URL used for UNIQUE comparison.

    Only call after validate_olx_url succeeded.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").encode("idna").decode("ascii").lower()

    path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    # Normalize percent-encoding: decode then re-encode with a stable charset.
    try:
        decoded_path = unquote(path, errors="strict")
    except UnicodeDecodeError:
        raise ValidationError("Некорректное кодирование пути.")
    path = quote(decoded_path, safe="/-_.~!$&'()*+,;=:@")

    raw_query = parts.query
    if raw_query:
        if _CONTROL_CHARS.search(raw_query):
            raise ValidationError("Query содержит недопустимые символы.")
        try:
            pairs = parse_qsl(
                raw_query, keep_blank_values=True, strict_parsing=False, errors="strict"
            )
        except UnicodeDecodeError:
            raise ValidationError("Некорректное кодирование query.")
        if len(pairs) > MAX_QUERY_PAIRS:
            raise ValidationError("Слишком много параметров query.")
        decoded_total = sum(len(k) + len(v) for k, v in pairs)
        if decoded_total > MAX_QUERY_DECODED_CHARS:
            raise ValidationError("Query длиннее допустимого.")
        kept = [(k, v) for k, v in pairs if not _is_tracking_key(k)]
        kept.sort(key=lambda pair: (pair[0], pair[1]))
        query = urlencode(kept, doseq=False)
    else:
        query = ""

    return urlunsplit((scheme, hostname, path, query, ""))


OLX_ID_PATTERN = re.compile(r"-ID([A-Za-z0-9]{4,32})\.html")


def extract_olx_id(url: str) -> str | None:
    match = OLX_ID_PATTERN.search(url or "")
    return match.group(1) if match else None
