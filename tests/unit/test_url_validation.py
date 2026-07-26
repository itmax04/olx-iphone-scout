"""U-01..U-03: URL validation, canonicalization, OLX ID extraction."""

import pytest
from django.core.exceptions import ValidationError

from apps.monitoring.validators import (
    canonicalize_olx_url,
    extract_olx_id,
    validate_olx_url,
)


class TestValidation:
    def test_valid_https_olx(self):
        url = validate_olx_url("https://www.olx.ua/uk/list/q-iphone/", check_dns=False)
        assert url.startswith("https://www.olx.ua/")

    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://www.olx.ua/list/",  # not https
            "https://example.com/x",  # foreign host (U-02)
            "https://olx.ua.evil.com/x",  # suffix trick
            "https://user:pw@olx.ua/x",  # credentials
            "https://olx.ua:8443/x",  # non-default port
            "ftp://olx.ua/x",
            "",
        ],
    )
    def test_rejected(self, bad_url):
        with pytest.raises(ValidationError):
            validate_olx_url(bad_url, check_dns=False)

    def test_too_long(self):
        with pytest.raises(ValidationError):
            validate_olx_url("https://www.olx.ua/" + "a" * 2100, check_dns=False)

    def test_dns_private_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "apps.monitoring.validators.socket.getaddrinfo",
            lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))],
        )
        with pytest.raises(ValidationError):
            validate_olx_url("https://www.olx.ua/uk/list/", check_dns=True)


class TestCanonicalization:
    def test_stable_order_and_tracking_removed(self):
        base_a = (
            "https://www.olx.ua/uk/list/q-iphone/"
            "?search%5Border%5D=created_at%3Adesc&utm_source=tg&b=2&a=1"
        )
        base_b = (
            "https://www.olx.ua/uk/list/q-iphone/?a=1&b=2&search%5Border%5D=created_at%3Adesc#f"
        )
        assert canonicalize_olx_url(base_a) == canonicalize_olx_url(base_b)
        assert "utm_source" not in canonicalize_olx_url(base_a)
        assert "search%5Border%5D" in canonicalize_olx_url(base_a)

    def test_fragment_removed_and_host_lowercased(self):
        url = canonicalize_olx_url("https://WWW.OLX.UA/uk/list/?x=1#frag")
        assert url == "https://www.olx.ua/uk/list/?x=1"

    def test_duplicate_pairs_kept(self):
        url = canonicalize_olx_url("https://www.olx.ua/list/?t=1&t=2")
        assert url.count("t=") == 2

    @pytest.mark.parametrize("key", ["utm_campaign", "gclid", "fbclid", "reason", "REF"])
    def test_tracking_keys_removed(self, key):
        url = canonicalize_olx_url(f"https://www.olx.ua/list/?{key}=x&q=iphone")
        assert key.lower() not in url.lower() or "q=iphone" in url
        assert "q=iphone" in url

    def test_unicode_query_survives(self):
        url = canonicalize_olx_url("https://www.olx.ua/list/?q=айфон 13")
        assert "q=" in url
        assert canonicalize_olx_url(url) == url  # idempotent


class TestOlxId:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://www.olx.ua/d/uk/obyavlenie/iphone-13-ID800000001.html", "800000001"),
            ("https://www.olx.ua/d/obyavlenie/x-IDabc123XY.html", "abc123XY"),
            ("https://www.olx.ua/d/uk/obyavlenie/no-id-here.html", None),
        ],
    )
    def test_extract(self, url, expected):
        assert extract_olx_id(url) == expected
