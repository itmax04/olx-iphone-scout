from django.urls import path

from apps.core import views

urlpatterns = [
    path("health/live/", views.health_live, name="health-live"),
    path("health/ready/", views.health_ready, name="health-ready"),
]
