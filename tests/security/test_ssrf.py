"""S-06: SSRF-защита URL поиска."""

import json

import pytest

pytestmark = pytest.mark.django_db

EVIL_URLS = [
    "https://evil.example.com/list",
    "https://olx.ua.evil.com/list",
    "http://olx.ua/list",
    "https://user:pass@www.olx.ua/list",
    "https://www.olx.ua:8080/list",
    "https://169.254.169.254/latest/meta-data/",
    "file:///etc/passwd",
]


@pytest.mark.parametrize("url", EVIL_URLS)
def test_profile_create_rejects_evil_url(admin_client_ru, url):
    body = {
        "name": "x",
        "olx_url": url,
        "target_models": ["iphone_13"],
        "target_storage_gb": [128],
        "max_purchase_price_uah": "10000.00",
    }
    response = admin_client_ru.post(
        "/api/v1/search-profiles/", data=json.dumps(body), content_type="application/json"
    )
    assert response.status_code == 400
    from apps.monitoring.models import SearchProfile

    assert SearchProfile.objects.count() == 0  # F-03: SSRF URL никогда не сохраняется


def test_dns_rebinding_to_private_ip_rejected(admin_client_ru, monkeypatch):
    monkeypatch.setattr(
        "apps.monitoring.validators.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))],
    )
    from django.core.exceptions import ValidationError

    from apps.monitoring.validators import validate_olx_url

    with pytest.raises(ValidationError):
        validate_olx_url("https://www.olx.ua/uk/list/", check_dns=True)


def test_no_arbitrary_fetch_endpoint(admin_client_ru):
    # В приложении нет endpoint'а, который бы скачивал произвольный URL.
    response = admin_client_ru.post(
        "/api/v1/search-profiles/test/",
        data=json.dumps({"olx_url": "https://evil.example.com/"}),
        content_type="application/json",
    )
    assert response.status_code == 400
