from django.urls import path

from apps.core import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.SafeLogoutView.as_view(), name="logout"),
    path("password_change/", views.password_change_view, name="password_change"),
]
