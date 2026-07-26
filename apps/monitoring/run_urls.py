from django.urls import path

from apps.monitoring import views

app_name = "runs"

urlpatterns = [
    path("", views.run_list, name="list"),
]
