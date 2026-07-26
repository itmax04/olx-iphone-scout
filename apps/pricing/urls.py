from django.urls import path

from apps.pricing import views

app_name = "prices"

urlpatterns = [
    path("", views.rules_list, name="list"),
    path("market/new/", views.market_rule_create, name="market_create"),
    path("market/<uuid:pk>/edit/", views.market_rule_edit, name="market_edit"),
    path("market/<uuid:pk>/deactivate/", views.market_rule_deactivate, name="market_deactivate"),
    path("defects/new/", views.defect_rule_create, name="defect_create"),
    path("defects/<uuid:pk>/edit/", views.defect_rule_edit, name="defect_edit"),
    path("defects/<uuid:pk>/deactivate/", views.defect_rule_deactivate, name="defect_deactivate"),
]
