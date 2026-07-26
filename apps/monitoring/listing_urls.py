from django.urls import path

from apps.monitoring import views

app_name = "listings"

urlpatterns = [
    path("", views.listing_list, name="list"),
    path("<uuid:pk>/", views.listing_detail, name="detail"),
    path("<uuid:pk>/status/", views.listing_set_status, name="set_status"),
    path("<uuid:pk>/reanalyze/", views.listing_reanalyze, name="reanalyze"),
]
