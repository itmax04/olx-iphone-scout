from django.urls import path

from apps.core import pages

app_name = "system"

urlpatterns = [
    path("", pages.system_page, name="index"),
    path("pause/", pages.pause_page_action, name="pause"),
    path("resume/", pages.resume_page_action, name="resume"),
    path("cleanup-preview/", pages.cleanup_preview_action, name="cleanup_preview"),
]
