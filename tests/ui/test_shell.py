"""UI shell: страницы рендерятся, навигация без dead links, локальные ассеты."""

import pytest

pytestmark = pytest.mark.django_db

PAGES = [
    "/dashboard/",
    "/searches/",
    "/searches/new/",
    "/listings/",
    "/prices/",
    "/prices/market/new/",
    "/prices/defects/new/",
    "/deals/",
    "/runs/",
    "/settings/",
    "/system/",
    "/accounts/password_change/",
]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders_for_admin(admin_client_ru, path):
    response = admin_client_ru.get(path)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'href="#"' not in html  # никаких dead buttons
    assert "cdn." not in html  # только локальные ассеты


@pytest.mark.parametrize("path", PAGES)
def test_page_redirects_anonymous(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/accounts/login/")


def test_root_redirects_to_dashboard(admin_client_ru):
    response = admin_client_ru.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard/"


def test_sidebar_links_resolve(admin_client_ru):
    html = admin_client_ru.get("/dashboard/").content.decode()
    for href in [
        "/searches/",
        "/listings/",
        "/prices/",
        "/deals/",
        "/runs/",
        "/settings/",
        "/system/",
    ]:
        assert f'href="{href}"' in html


def test_empty_dashboard_honest(admin_client_ru):
    html = admin_client_ru.get("/dashboard/").content.decode()
    assert "Начните с настройки" in html  # честный empty state, не фальшивые цифры
