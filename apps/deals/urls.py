from django.urls import path

from apps.deals import views

app_name = "deals"

urlpatterns = [
    path("", views.deal_list, name="list"),
    path("new/", views.deal_create, name="create"),
    path("export.csv", views.deal_export_csv, name="export_csv"),
    path("<uuid:pk>/edit/", views.deal_edit, name="edit"),
]
