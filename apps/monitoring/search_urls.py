from django.urls import path

from apps.monitoring import views

app_name = "searches"

urlpatterns = [
    path("", views.search_list, name="list"),
    path("new/", views.search_create, name="create"),
    path("test-url/", views.search_test_url, name="test_url"),
    path("<uuid:pk>/edit/", views.search_edit, name="edit"),
    path("<uuid:pk>/run/", views.search_run_now, name="run"),
    path("<uuid:pk>/toggle/", views.search_toggle, name="toggle"),
    path("<uuid:pk>/archive/", views.search_archive, name="archive"),
]
