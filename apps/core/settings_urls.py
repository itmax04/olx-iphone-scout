from django.urls import path

from apps.core import pages

app_name = "app_settings"

urlpatterns = [
    path("", pages.settings_page, name="index"),
    path("telegram-test/", pages.telegram_test_action, name="telegram_test"),
    path("openai-check/", pages.openai_check_action, name="openai_check"),
]
